"""Reddit distribution through Composio OAuth.

Reddit posting is intentionally conservative: a strict subreddit allowlist,
a cooldown, and text-first posts with a source link. Keep DIST_REDDIT=false
until you have manually reviewed the target communities.
"""
from __future__ import annotations

from . import composio_reddit
from .base import PostPayload


def post(payload: PostPayload) -> None:
    composio_reddit.post(payload)
