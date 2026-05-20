from __future__ import annotations

import os

import requests
from atproto import Client as BlueskyClient

from ..logging_utils import log
from .base import PostPayload


def post(payload: PostPayload) -> None:
    user = os.getenv("BLUESKY_USER")
    pw = os.getenv("BLUESKY_PASS")
    if not (user and pw):
        log.info("bluesky.skip reason=no_credentials")
        return
    try:
        client = BlueskyClient()
        client.login(login=user, password=pw)
        embed = None
        if payload.image_url:
            thumb_blob = client.upload_blob(requests.get(payload.image_url, timeout=30).content).blob
            embed = {
                "$type": "app.bsky.embed.external",
                "external": {
                    "uri": payload.url,
                    "title": payload.title[:120],
                    "description": payload.excerpt[:200],
                    "thumb": thumb_blob,
                },
            }
        client.send_post(text=payload.short_social_text[:300], embed=embed)
        log.info("bluesky.post ok url=%s", payload.url)
    except Exception as exc:
        log.warning("bluesky.post err=%s", exc)
