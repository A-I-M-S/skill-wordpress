"""Backward-compatible shim for the legacy socialMedia.py module.

The real distributors now live under `openclaw/distribution/`. This file
re-exports the most commonly imported names so any external scripts
referring to `socialMedia.post_to_linkedin(...)` still work.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Legacy module-level constants
WP_HOST = os.getenv("WP_HOST")
WP_USER = os.getenv("WP_USER")
WP_PW = os.getenv("WP_PW")
CATEGORY_FILE = Path(__file__).resolve().parent / "data" / "curated_categories.json"

# --- legacy adapters -------------------------------------------------------
from openclaw.distribution.base import PostPayload  # noqa: E402
from openclaw.indexing import submit_indexnow as _submit_indexnow  # noqa: E402


def _payload(url: str, content: str, image_url: str | None = None) -> PostPayload:
    return PostPayload(
        title="(legacy)",
        excerpt=content[:160],
        url=url,
        html_content=content,
        md_content=content,
        tags=[],
        image_url=image_url,
    )


def submit_to_indexnow(urls):
    _submit_indexnow(urls)


def post_to_linkedin(content: str):
    from openclaw.distribution import linkedin
    linkedin.post(_payload(url="", content=content))


def post_to_threads(content: str, image_url: str | None = None):
    from openclaw.distribution import threads
    threads.post(_payload(url="", content=content, image_url=image_url))


def post_to_facebook(content: str):
    from openclaw.distribution import facebook
    facebook.post(_payload(url="", content=content))


def post_to_telegram(content: str):
    from openclaw.distribution import telegram
    telegram.post(_payload(url="", content=content))


def post_to_discord(content: str):
    from openclaw.distribution import discord
    discord.post(_payload(url="", content=content))


def post_to_bluesky(content: str, url: str, image_url: str | None = None):
    from openclaw.distribution import bluesky
    bluesky.post(_payload(url=url, content=content, image_url=image_url))


def post_to_dev(title, md_content, url):
    # Intentionally disabled by default — see openclaw.config.DistributionFlags.devto.
    pass


def post_to_wordpress_com(title, content):
    # Intentionally disabled by default — duplicate-content footgun.
    pass


async def nostr_post_async(content: str):
    from openclaw.distribution import nostr as _n
    await _n._post_async(content)  # type: ignore[attr-defined]
