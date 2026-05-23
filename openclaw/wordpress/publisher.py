"""Post-publish orchestration: build HTML, inject SEO blocks, publish, save state."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..config import settings
from ..images.seedream import SeedreamClient, build_blog_hero_prompt
from ..llm import GeneratedArticle
from ..logging_utils import log
from ..seo import (
    build_article_schema,
    inject_author_block,
    load_recent_titles,
    is_duplicate_title,
    primary_keyword,
)
from .client import WordPressClient


@dataclass
class PublishedPost:
    id: int
    url: str
    title: str
    excerpt: str
    featured_media_url: Optional[str]
    category_id: int

    def to_state_entry(self) -> dict:
        d = asdict(self)
        d["published_at"] = datetime.now(timezone.utc).isoformat()
        return d


class Publisher:
    def __init__(self, wp: Optional[WordPressClient] = None) -> None:
        self.wp = wp or WordPressClient()
        self.state_file: Path = settings.publishing.state_file

    # ---- state ----
    def _load_state(self) -> dict:
        if not self.state_file.exists():
            return {"recent_posts": []}
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return {"recent_posts": []}

    def _save_state(self, state: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, indent=2))

    def _append_state(self, entry: PublishedPost) -> None:
        state = self._load_state()
        state.setdefault("recent_posts", []).append(entry.to_state_entry())
        state["recent_posts"] = state["recent_posts"][-500:]
        self._save_state(state)

    def has_quota(self) -> bool:
        state = self._load_state()
        today = datetime.now(timezone.utc).date().isoformat()
        recent = state.get("recent_posts", [])
        todays = [p for p in recent if p.get("published_at", "").startswith(today)]
        if len(todays) >= settings.publishing.max_posts_per_day:
            log.warning(
                "publisher.quota EXCEEDED today=%d cap=%d",
                len(todays),
                settings.publishing.max_posts_per_day,
            )
            return False

        if recent:
            last = recent[-1].get("published_at")
            if last:
                last_dt = datetime.fromisoformat(last)
                elapsed_min = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
                if elapsed_min < settings.publishing.min_minutes_between_posts:
                    log.warning(
                        "publisher.cooldown elapsed_min=%.1f min=%d",
                        elapsed_min,
                        settings.publishing.min_minutes_between_posts,
                    )
                    return False
        return True

    # ---- featured image ----
    def _resolve_featured_image(self, article: GeneratedArticle) -> tuple[Optional[int], Optional[str]]:
        """Try Seedream first; fall back to legacy media-ID roulette."""
        if settings.seedream.api_key:
            try:
                client = SeedreamClient()
                prompt = build_blog_hero_prompt(article.title, article.tags)
                img = client.generate(prompt)
                kw = primary_keyword(article.tags, article.title)
                if img.saved_to:
                    media = self.wp.upload_media(
                        img.saved_to,
                        alt_text=f"{kw} — illustration for {article.title}",
                        title=article.title[:80],
                    )
                    return media["id"], media.get("source_url")
            except Exception as exc:
                log.warning("publisher.seedream_failed err=%s; falling back to media roulette", exc)

        # Fallback: legacy random media ID
        import random
        wp_cfg = settings.wp
        media_id = random.randrange(wp_cfg.media_range_start, wp_cfg.media_range_end)
        try:
            media = self.wp.get_media(media_id)
            return media_id, media.get("source_url")
        except Exception as exc:
            log.warning("publisher.fallback_media err=%s", exc)
            return None, None

    # ---- main entry ----
    def publish(
        self,
        article: GeneratedArticle,
        category_id: int,
        enforce_quota: bool = True,
    ) -> PublishedPost:
        if enforce_quota and not self.has_quota():
            raise RuntimeError("daily quota or min-interval not satisfied")

        # Dedup against recent titles
        existing_titles = load_recent_titles(self.state_file)
        if is_duplicate_title(article.title, existing_titles):
            raise RuntimeError(f"duplicate-similar title detected: {article.title!r}")

        # Featured image
        media_id, image_url = self._resolve_featured_image(article)

        # Enrich content. Internal links are added by scripts.publish before publishing;
        # keep Publisher from adding a duplicate related-reading block.
        body = inject_author_block(article.content)

        # Tags
        tag_ids = self.wp.ensure_tags(article.tags)

        # Publish first to obtain URL, then patch in schema
        post = self.wp.create_post(
            title=article.title,
            content=body,
            excerpt=article.excerpt,
            category_ids=[category_id],
            tag_ids=tag_ids,
            featured_media_id=media_id,
        )

        # Append JSON-LD schema using the now-known URL
        schema_block = build_article_schema(
            article.title, article.excerpt, post["link"], image_url
        )
        try:
            import requests
            from requests.auth import HTTPBasicAuth
            requests.post(
                f"{self.wp.base}/posts/{post['id']}",
                auth=HTTPBasicAuth(settings.wp.user, settings.wp.password),
                json={"content": body + schema_block},
                timeout=30,
            )
        except Exception as exc:
            log.warning("publisher.schema_patch err=%s", exc)

        published = PublishedPost(
            id=post["id"],
            url=post["link"],
            title=article.title,
            excerpt=article.excerpt,
            featured_media_url=image_url,
            category_id=category_id,
        )
        self._append_state(published)
        return published
