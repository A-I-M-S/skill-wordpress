from __future__ import annotations

import os

import requests

from ..logging_utils import log
from .base import PostPayload


def post(payload: PostPayload, custom_text: str | None = None) -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        log.info("telegram.skip reason=no_credentials")
        return
    text = custom_text or payload.social_text
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        log.info("telegram.post ok url=%s", payload.url)
    except Exception as exc:
        log.warning("telegram.post err=%s", exc)


def send_raw(text: str, chat_id_override: str | None = None) -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = chat_id_override or os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
    except Exception as exc:
        log.warning("telegram.send_raw err=%s", exc)
