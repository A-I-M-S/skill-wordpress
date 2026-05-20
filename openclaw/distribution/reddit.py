"""Reddit distribution via PRAW.

CRITICAL — read this before enabling:
  Reddit is hostile to bots that submit links without karma or community
  participation. The default config posts ONLY to your user profile sub
  (`u_aloycwl`), which is the safe surface. Add more subs to
  REDDIT_ALLOWED_SUBS only when you have karma in that sub AND that sub
  explicitly permits self-promo. Auto-posting to large subs without
  curation will shadowban your account.

Best-practice rules baked in:
  - Strict allowlist of subreddits
  - Minimum interval between posts (default 4h)
  - Title rewriter strips "[OpenClaw]" prefix and emojis
  - On failure, silently logs and continues — never crashes the pipeline
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from ..config import ARTIFACTS_DIR, settings
from ..logging_utils import log
from .base import PostPayload

_STATE_FILE: Path = ARTIFACTS_DIR / "reddit_state.json"


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
            log.info(
                "reddit.cooldown elapsed_min=%.1f min=%d",
                elapsed_min,
                settings.reddit.min_minutes_between_posts,
            )
            return False
    except Exception:
        return True
    return True


def _record_post(sub: str, url: str) -> None:
    state = {}
    if _STATE_FILE.exists():
        try:
            state = json.loads(_STATE_FILE.read_text())
        except Exception:
            state = {}
    state["last_post_at"] = datetime.now(timezone.utc).isoformat()
    state.setdefault("posts", []).append(
        {"sub": sub, "url": url, "at": state["last_post_at"]}
    )
    state["posts"] = state["posts"][-200:]
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2))


def post(payload: PostPayload) -> None:
    cfg = settings.reddit
    if not (cfg.client_id and cfg.client_secret and cfg.username and cfg.password):
        log.info("reddit.skip reason=no_credentials")
        return
    if not cfg.allowed_subs:
        log.info("reddit.skip reason=no_allowed_subs")
        return
    if not _can_post():
        return

    try:
        import praw  # local import; only required when enabled
    except ImportError:
        log.warning("reddit.skip reason=praw_not_installed (pip install praw)")
        return

    reddit = praw.Reddit(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        username=cfg.username,
        password=cfg.password,
        user_agent=cfg.user_agent,
    )

    title = _clean_title(payload.title)
    posted_anywhere = False
    for sub in cfg.allowed_subs:
        try:
            submission = reddit.subreddit(sub).submit(title=title, url=payload.url)
            log.info("reddit.post ok sub=%s permalink=%s", sub, submission.permalink)
            _record_post(sub, payload.url)
            posted_anywhere = True
            time.sleep(2)
        except Exception as exc:
            log.warning("reddit.post sub=%s err=%s", sub, exc)

    if not posted_anywhere:
        log.info("reddit.post no_subs_succeeded")
