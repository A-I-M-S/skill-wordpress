"""Blogger teaser distribution.

Posts short canonical teasers to Blogspot. Never mirrors the full article.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from ..config import ARTIFACTS_DIR, settings
from ..logging_utils import log
from .base import PostPayload

SCOPES = ["https://www.googleapis.com/auth/blogger"]
_STATE_FILE = ARTIFACTS_DIR / "blogger_state.json"


def _clean(text: str, limit: int | None = None) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip() if limit else text


def _utm(url: str) -> str:
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("utm_source", "blogspot")
    query.setdefault("utm_medium", "syndication")
    query.setdefault("utm_campaign", "seo_teaser")
    return urlunparse(parts._replace(query=urlencode(query)))


def _state() -> dict[str, Any]:
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    _STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


def _can_post(url: str) -> bool:
    cfg = settings.blogger
    state = _state()
    if url in state.get("posted_urls", {}):
        log.info("blogger.skip reason=already_posted url=%s", url)
        return False
    today = datetime.now(timezone.utc).date().isoformat()
    if state.get("posted_by_day", {}).get(today, 0) >= cfg.max_per_day:
        log.info("blogger.skip reason=daily_cap cap=%d", cfg.max_per_day)
        return False
    last = state.get("last_post_at")
    if last:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 60
        if elapsed < cfg.min_minutes_between_posts:
            log.info("blogger.skip reason=cooldown elapsed=%.1f min=%d", elapsed, cfg.min_minutes_between_posts)
            return False
    return True


def _record(url: str, blogger_url: str | None) -> None:
    state = _state()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    state.setdefault("posted_urls", {})[url] = {"at": now.isoformat(), "blogger_url": blogger_url}
    state.setdefault("posted_by_day", {})[today] = state.setdefault("posted_by_day", {}).get(today, 0) + 1
    state["last_post_at"] = now.isoformat()
    _save_state(state)


def credentials() -> Credentials:
    cfg = settings.blogger
    token_path = Path(cfg.token_file)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    if not creds or not creds.valid:
        raise RuntimeError(
            f"Blogger OAuth token missing/invalid. Run: python3 -m scripts.blogger_auth --console"
        )
    return creds


def service():
    return build("blogger", "v3", credentials=credentials(), cache_discovery=False)


def resolve_blog_id() -> str:
    cfg = settings.blogger
    if cfg.blog_id:
        return cfg.blog_id
    svc = service()
    blog = svc.blogs().getByUrl(url=cfg.blog_url).execute()
    blog_id = blog.get("id")
    if not blog_id:
        raise RuntimeError(f"Could not resolve Blogger blog id for {cfg.blog_url}")
    log.info("blogger.resolved blog_id=%s url=%s", blog_id, cfg.blog_url)
    return blog_id


def build_teaser(payload: PostPayload) -> str:
    title = _clean(payload.title)
    excerpt = _clean(payload.excerpt or payload.md_content, 360)
    target = _utm(payload.url)
    safe_title = html.escape(title)
    safe_excerpt = html.escape(excerpt)
    safe_url = html.escape(target, quote=True)
    return f"""
<p><strong>New on InsightGinie:</strong> {safe_title}</p>
<p>{safe_excerpt}</p>
<p><a href=\"{safe_url}\" rel=\"canonical noopener\" target=\"_blank\">Read the full canonical article on InsightGinie</a>.</p>
<hr>
<p><em>This Blogspot post is a short teaser. The full version lives on InsightGinie.</em></p>
""".strip()


def post(payload: PostPayload) -> None:
    cfg = settings.blogger
    if not (cfg.enabled and settings.distribution.blogger):
        log.info("blogger.skip reason=disabled")
        return
    if not _can_post(payload.url):
        return
    try:
        svc = service()
        blog_id = resolve_blog_id()
        body = {
            "kind": "blogger#post",
            "title": f"New on InsightGinie: {_clean(payload.title, 90)}",
            "content": build_teaser(payload),
            "labels": cfg.labels,
        }
        result = svc.posts().insert(blogId=blog_id, body=body, isDraft=cfg.draft).execute()
        blogger_url = result.get("url")
        _record(payload.url, blogger_url)
        log.info("blogger.post ok draft=%s url=%s", cfg.draft, blogger_url)
    except Exception as exc:
        log.warning("blogger.post err=%s", exc)
