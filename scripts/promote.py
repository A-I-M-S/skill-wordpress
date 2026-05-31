"""Promote an EXISTING post (no new publishing).

Strategy: pick a recent post, regenerate a fresh angle for the social
caption, regenerate a Seedream promo image, and fan out. This is what
drives traffic to your 8k existing posts without adding new ones — the
single highest-leverage thing you can do while pruning the back catalog.

Usage:
    python -m scripts.promote                          # random recent post
    python -m scripts.promote --url https://insightginie.com/foo/
    python -m scripts.promote --shorts                 # also generate YT Short
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import html2text
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw.config import settings  # noqa: E402
from openclaw.distribution import (
    blogger,  # noqa: E402
    bluesky,
    discord,
    facebook,
    hackernews,
    linkedin,
    reddit,
    telegram,
    threads,
    youtube_shorts,
)
from openclaw.distribution.base import PostPayload  # noqa: E402
from openclaw.images.seedream import SeedreamClient, build_blog_hero_prompt  # noqa: E402
from openclaw.indexing import submit_indexnow  # noqa: E402
from openclaw.logging_utils import log  # noqa: E402
from openclaw.wordpress.client import WordPressClient  # noqa: E402


def _rewrite_caption(title: str, excerpt: str) -> str:
    """Use OpenRouter to write a fresh, casual caption — different each share."""
    api_key = settings.llm.openrouter_key
    if not api_key:
        return f"{title}\n\n{excerpt}"
    prompt = (
        "Write a 2-sentence social caption for the article below. Conversational "
        "tone, no emojis, no hashtags. Lead with a hook, end with curiosity. "
        f"Return raw text only.\n\nTitle: {title}\nExcerpt: {excerpt}"
    )
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": settings.llm.primary_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
            },
            timeout=60,
        )
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.warning("promote.caption err=%s", exc)
        return f"{title}\n\n{excerpt}"


def _fetch_post(url: Optional[str]) -> dict:
    wp = WordPressClient()
    if url:
        slug = url.rstrip("/").split("/")[-1]
        results = requests.get(
            f"{wp.base}/posts",
            params={"slug": slug, "_embed": 1},
            auth=wp.auth,
            timeout=30,
        ).json()
        if not results:
            raise SystemExit(f"no post found for url={url}")
        return results[0]
    post = wp.random_post()
    if not post:
        raise SystemExit("no posts available")
    return post


def _placeholder_image_url(title: str, tags: list[str]) -> Optional[str]:
    try:
        import re
        from PIL import Image, ImageDraw, ImageFont
        from openclaw.config import ARTIFACTS_DIR

        out_dir = ARTIFACTS_DIR / "promo-placeholders"
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"\W+", "-", title.lower()).strip("-")[:60] or "promo"
        path = out_dir / f"{slug}.png"

        img = Image.new("RGB", (1600, 900), (11, 18, 32))
        draw = ImageDraw.Draw(img)
        for y in range(900):
            shade = int(18 + y * 35 / 900)
            draw.line([(0, y), (1600, y)], fill=(11, shade, 48))
        for x, y, r, color in [(1250, 180, 260, (36, 99, 235)), (260, 720, 220, (14, 165, 233))]:
            draw.ellipse((x-r, y-r, x+r, y+r), fill=color)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle((90, 90, 1510, 810), fill=(2, 6, 23, 190), outline=(148, 163, 184, 120), width=3)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
        font_path = next((fp for fp in font_paths if Path(fp).exists()), None)
        title_font = ImageFont.truetype(font_path, 64) if font_path else ImageFont.load_default()
        tag_font = ImageFont.truetype(font_path, 32) if font_path else ImageFont.load_default()
        words = title.split()
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if draw.textbbox((0, 0), test, font=title_font)[2] <= 1180:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        lines = lines[:4]
        y = 260
        for line in lines:
            draw.text((170, y), line, font=title_font, fill=(248, 250, 252))
            y += 82
        tag_text = " • ".join([t for t in tags[:3] if t]) or "InsightGinie"
        draw.text((170, 650), tag_text, font=tag_font, fill=(125, 211, 252))
        draw.text((170, 710), "insightginie.com", font=tag_font, fill=(203, 213, 225))
        img.save(path, quality=92)
        wp = WordPressClient()
        media = wp.upload_media(path, alt_text=f"Promo for {title}", title=title[:80])
        return media.get("source_url")
    except Exception as exc:
        log.warning("promote.placeholder_image err=%s", exc)
        return None


def _refresh_image(title: str, tags: list[str]) -> Optional[str]:
    if not settings.seedream.api_key:
        return None
    try:
        client = SeedreamClient()
        prompt = build_blog_hero_prompt(title, tags)
        img = client.generate(prompt)
        if img.saved_to:
            wp = WordPressClient()
            media = wp.upload_media(
                img.saved_to,
                alt_text=f"Promo for {title}",
                title=title[:80],
            )
            return media.get("source_url")
    except Exception as exc:
        log.warning("promote.image err=%s", exc)
        return _placeholder_image_url(title, tags)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenClaw promote-existing-post.")
    parser.add_argument("--url", type=str, default=None, help="Promote a specific post URL.")
    parser.add_argument("--shorts", action="store_true", help="Also generate a YouTube Short.")
    args = parser.parse_args()

    post = _fetch_post(args.url)
    title = post.get("title", {}).get("rendered", "Untitled")
    import re as _re
    excerpt_raw = post.get("excerpt", {}).get("rendered", "")
    excerpt = _re.sub(r"<[^>]+>", "", excerpt_raw).strip()
    content_html = post.get("content", {}).get("rendered", "")
    post_url = post.get("link")

    tags: list[str] = []
    embedded = post.get("_embedded", {}).get("wp:term", [])
    for group in embedded:
        for term in group:
            if term.get("taxonomy") == "post_tag":
                tags.append(term.get("name", ""))

    log.info("promote.target url=%s title=%r", post_url, title)

    fresh_image = _refresh_image(title, tags) or post.get("jetpack_featured_media_url")
    fresh_caption = _rewrite_caption(title, excerpt)

    payload = PostPayload(
        title=title,
        excerpt=fresh_caption,
        url=post_url,
        html_content=content_html,
        md_content=html2text.html2text(content_html),
        tags=tags,
        image_url=fresh_image,
    )

    submit_indexnow([post_url])

    flags = settings.distribution
    if flags.linkedin: linkedin.post(payload)
    if flags.bluesky: bluesky.post(payload)
    if flags.threads: threads.post(payload)
    if flags.facebook: facebook.post(payload)
    if flags.telegram: telegram.post(payload)
    if flags.discord: discord.post(payload)
    if flags.reddit: reddit.post(payload)
    if flags.hackernews: hackernews.post(payload)
    if flags.blogger: blogger.post(payload)
    if args.shorts or flags.youtube_shorts:
        youtube_shorts.post(payload)

    log.info("promote.done url=%s", post_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
