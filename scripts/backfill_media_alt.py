"""Backfill missing/generic featured-image alt text from post titles.

Usage:
    python scripts/backfill_media_alt.py --limit 500 --dry-run
    python scripts/backfill_media_alt.py --limit 500
"""
from __future__ import annotations

import argparse
import re
import sys
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw.wordpress.client import WordPressClient  # noqa: E402

GENERIC_ALT = {"", "image", "blog image", "generated image", "illustration", "photo", "picture"}


def clean_text(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("rendered", "")
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", unescape(text)).strip()


def needs_alt(alt: str) -> bool:
    normalized = re.sub(r"\s+", " ", (alt or "").strip().lower())
    return normalized in GENERIC_ALT or normalized.startswith("generated ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill featured-image alt text.")
    parser.add_argument("--limit", type=int, default=500, help="Maximum posts to inspect.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
    args = parser.parse_args()

    wp = WordPressClient()
    inspected = updated = skipped = 0
    seen_media: set[int] = set()
    page = 1
    while inspected < args.limit:
        posts = wp.list_posts(page=page, per_page=min(100, args.limit - inspected), _fields="id,title,link,featured_media")
        if not posts:
            break
        for post in posts:
            inspected += 1
            media_id = int(post.get("featured_media") or 0)
            if not media_id or media_id in seen_media:
                skipped += 1
                continue
            seen_media.add(media_id)
            try:
                media = wp.get_media(media_id)
            except Exception as exc:
                print(f"skip post={post.get('id')} media={media_id} err={exc}")
                skipped += 1
                continue
            current_alt = media.get("alt_text") or ""
            if not needs_alt(current_alt):
                skipped += 1
                continue
            title = clean_text(post.get("title", ""))
            alt = f"{title} — Insight Ginie illustration"[:160].rstrip(" -—")
            print(f"{'would_update' if args.dry_run else 'update'} media={media_id} post={post.get('id')} alt={alt!r}")
            if not args.dry_run:
                wp.update_media_metadata(media_id, alt_text=alt, title=title[:80])
            updated += 1
        page += 1
    print(f"inspected={inspected} updated={updated} skipped={skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
