"""Hacker News semi-automation.

WHY SEMI-AUTOMATED:
  HN's official API (firebaseio.com) is READ-ONLY. There is no supported
  way to submit posts via API. Scraping the submit form risks an account
  shadowban — once `[dead]`, HN never resurrects an account.

WHAT THIS MODULE DOES:
  Builds a pre-filled HN submission URL and delivers it via Telegram
  (chat ID = HN_NOTIFY_TELEGRAM_CHAT_ID, falls back to TELEGRAM_CHAT_ID).
  You tap the link, glance at the title, and submit with one tap from
  your phone or browser. This preserves account quality and is far more
  effective than auto-spamming.

PRO TIPS:
  - Best submission window: ~07:30 UTC and ~14:00 UTC (peak HN traffic).
  - Submit your strongest 1-2 posts per WEEK, not per day.
  - Title should be calm and informative — HN hates marketing language.
"""
from __future__ import annotations

import os
from urllib.parse import quote

from ..config import settings
from ..logging_utils import log
from . import telegram as tg
from .base import PostPayload


def build_submit_url(title: str, url: str) -> str:
    return (
        f"https://news.ycombinator.com/submitlink?u={quote(url, safe='')}"
        f"&t={quote(title[:80], safe='')}"
    )


def _hn_friendly_title(title: str) -> str:
    # Strip marketing prefixes / emojis — HN downvotes anything that looks like a press release.
    import re
    t = re.sub(r"^\[OpenClaw\]\s*", "", title, flags=re.I)
    t = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if t.lower().startswith(("the ", "a ", "an ")):
        return t
    return t


def post(payload: PostPayload) -> None:
    if not settings.hn.enabled:
        return
    chat_id = settings.hn.notify_chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        log.info("hn.skip reason=no_telegram_chat")
        return
    title = _hn_friendly_title(payload.title)
    submit_url = build_submit_url(title, payload.url)
    message = (
        "🟧 HN submission candidate\n\n"
        f"Title: {title}\n"
        f"URL:   {payload.url}\n\n"
        f"One-click submit:\n{submit_url}\n\n"
        "Skip if title is weak. Best slots: 07:30 / 14:00 UTC."
    )
    tg.send_raw(message, chat_id_override=chat_id)
    log.info("hn.notify_sent url=%s", payload.url)
