"""Main entrypoint — generate one article and fan it out across distributors.

Usage:
    python -m scripts.publish              # publish + distribute
    python -m scripts.publish --dry-run    # generate + print, no publish
    python -m scripts.publish --category 16  # force a specific category ID
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Optional

import html2text

# Allow `python scripts/publish.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw.config import settings  # noqa: E402
from openclaw.distribution import (  # noqa: E402
    bluesky,
    discord,
    facebook,
    hackernews,
    hashnode,
    linkedin,
    nostr,
    reddit,
    telegram,
    threads,
    youtube_shorts,
)
from openclaw.distribution.base import PostPayload  # noqa: E402
from openclaw.indexing import submit_bing, submit_indexnow  # noqa: E402
from openclaw.llm import LLMClient  # noqa: E402
from openclaw.logging_utils import log  # noqa: E402
from openclaw.trends import fetch_trending_topic  # noqa: E402
from openclaw.wordpress.publisher import Publisher  # noqa: E402


def pick_category(forced_id: Optional[int]) -> dict:
    cats = json.loads(settings.publishing.category_file.read_text())
    if forced_id is not None:
        for cat in cats:
            if cat["id"] == forced_id:
                return cat
        raise SystemExit(f"category id {forced_id} not in {settings.publishing.category_file}")
    return random.choice(cats)


def fan_out(payload: PostPayload) -> None:
    flags = settings.distribution
    if flags.linkedin:
        linkedin.post(payload)
    if flags.bluesky:
        bluesky.post(payload)
    if flags.threads:
        threads.post(payload)
    if flags.facebook:
        facebook.post(payload)
    if flags.telegram:
        telegram.post(payload)
    if flags.discord:
        discord.post(payload)
    if flags.nostr:
        nostr.post(payload)
    if flags.hashnode:
        hashnode.post(payload)
    if flags.reddit:
        reddit.post(payload)
    if flags.hackernews:
        hackernews.post(payload)
    if flags.youtube_shorts:
        youtube_shorts.post(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenClaw publish + distribute.")
    parser.add_argument("--category", type=int, default=None, help="Force category ID.")
    parser.add_argument("--dry-run", action="store_true", help="Generate but do not publish.")
    parser.add_argument("--skip-distribution", action="store_true", help="Publish but skip social fan-out.")
    args = parser.parse_args()

    category = pick_category(args.category)
    log.info("publish.start category=%s id=%d", category["name"], category["id"])

    topic = fetch_trending_topic(category["name"])
    article = LLMClient().generate_article(topic)
    log.info("publish.generated words=%d title=%r", len(article.content.split()), article.title)

    if args.dry_run:
        print(json.dumps({
            "title": article.title,
            "excerpt": article.excerpt,
            "tags": article.tags,
            "word_count": len(article.content.split()),
        }, indent=2))
        return 0

    publisher = Publisher()
    if not publisher.has_quota():
        log.warning("publish.aborted reason=quota_or_cooldown")
        return 1
    published = publisher.publish(article, category_id=category["id"])

    md_content = html2text.html2text(article.content)
    payload = PostPayload(
        title=published.title,
        excerpt=published.excerpt,
        url=published.url,
        html_content=article.content,
        md_content=md_content,
        tags=article.tags,
        image_url=published.featured_media_url,
    )

    submit_indexnow([published.url])
    submit_bing([published.url])

    if not args.skip_distribution:
        fan_out(payload)

    log.info("publish.done url=%s", published.url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
