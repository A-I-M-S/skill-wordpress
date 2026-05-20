"""Distribution channels. Each module exposes a `post(...)` function with
a consistent signature so they can be fanned out from scripts/publish.py."""
from . import (
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

__all__ = [
    "bluesky",
    "discord",
    "facebook",
    "hackernews",
    "hashnode",
    "linkedin",
    "nostr",
    "reddit",
    "telegram",
    "threads",
    "youtube_shorts",
]
