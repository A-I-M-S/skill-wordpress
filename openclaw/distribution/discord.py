from __future__ import annotations

import os

import requests

from ..logging_utils import log
from .base import PostPayload


def post(payload: PostPayload) -> None:
    token = os.getenv("DISCORD_TOKEN")
    channel = os.getenv("DISCORD_CHANNEL_ID")
    if not (token and channel):
        log.info("discord.skip reason=no_credentials")
        return
    try:
        requests.post(
            f"https://discord.com/api/v10/channels/{channel}/messages",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"content": payload.social_text},
            timeout=15,
        )
        log.info("discord.post ok url=%s", payload.url)
    except Exception as exc:
        log.warning("discord.post err=%s", exc)
