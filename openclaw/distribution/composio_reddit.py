"""Reddit distribution through Composio OAuth.

Default posture is conservative: only post to the configured allowlist and obey
cooldowns. Reddit is for community participation, not link blasting.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..composio_client import ComposioClient, available as composio_available
from ..config import ARTIFACTS_DIR, settings
from ..logging_utils import log
from ..social_copy import rewrite, utm_url
from .base import PostPayload

_STATE_FILE: Path = ARTIFACTS_DIR / "composio_reddit_state.json"


def _clean_title(title: str) -> str:
    t = re.sub(r"^\[OpenClaw\]\s*", "", title, flags=re.I)
    t = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:300]


def _can_post() -> bool:
    if not _STATE_FILE.exists():
        return True
    try:
        state = json.loads(_STATE_FILE.read_text())
        last = state.get("last_post_at")
        if not last:
            return True
        elapsed_min = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 60
        if elapsed_min < settings.reddit.min_minutes_between_posts:
            log.info("composio_reddit.cooldown elapsed_min=%.1f min=%d", elapsed_min, settings.reddit.min_minutes_between_posts)
            return False
    except Exception:
        return True
    return True


def _record_post(sub: str, url: str, detail: str | None = None) -> None:
    state = {}
    if _STATE_FILE.exists():
        try:
            state = json.loads(_STATE_FILE.read_text())
        except Exception:
            state = {}
    state["last_post_at"] = datetime.now(timezone.utc).isoformat()
    state.setdefault("posts", []).append({"sub": sub, "url": url, "detail": detail or "", "at": state["last_post_at"]})
    state["posts"] = state["posts"][-200:]
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2))


def post(payload: PostPayload) -> None:
    if not (composio_available() and settings.composio.reddit_account_id):
        log.info("composio_reddit.skip reason=not_configured")
        return
    if not settings.reddit.allowed_subs:
        log.info("composio_reddit.skip reason=no_allowed_subs")
        return
    if not _can_post():
        return

    client = ComposioClient()
    title = _clean_title(payload.title)
    target_url = utm_url(payload.url, source="reddit")
    body = rewrite(payload.title, payload.excerpt, channel="reddit", url=target_url)
    body = f"{body}\n\nSource: {target_url}"

    posted_anywhere = False
    for sub in settings.reddit.allowed_subs:
        result = client.execute(
            "REDDIT_CREATE_REDDIT_POST",
            connected_account_id=settings.composio.reddit_account_id,
            arguments={
                "subreddit": sub,
                "title": title,
                "kind": "self",
                "text": body[:39000],
            },
        )
        if result.successful:
            log.info("composio_reddit.post ok sub=%s data=%s", sub, result.data)
            _record_post(sub, target_url, str(result.data)[:500])
            posted_anywhere = True
        else:
            log.warning("composio_reddit.post sub=%s err=%s", sub, result.error)

    if not posted_anywhere:
        log.info("composio_reddit.post no_subs_succeeded")
