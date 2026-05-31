"""Reddit distribution via the direct Reddit API (script-app OAuth password grant).

Conservative posture preserved: strict subreddit allowlist, a cooldown, and
text-first self-posts with a source link. Requires REDDIT_CLIENT_ID,
REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD in the environment;
skips gracefully if any are missing.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from ..config import ARTIFACTS_DIR, settings
from ..logging_utils import log
from ..social_copy import rewrite, utm_url
from .base import PostPayload

_STATE_FILE: Path = ARTIFACTS_DIR / "reddit_state.json"
_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_SUBMIT_URL = "https://oauth.reddit.com/api/submit"


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
            log.info("reddit.cooldown elapsed_min=%.1f min=%d", elapsed_min, settings.reddit.min_minutes_between_posts)
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


def _access_token(ua: str) -> str | None:
    cid = os.getenv("REDDIT_CLIENT_ID")
    secret = os.getenv("REDDIT_CLIENT_SECRET")
    user = os.getenv("REDDIT_USERNAME")
    pw = os.getenv("REDDIT_PASSWORD")
    if not all([cid, secret, user, pw]):
        log.info("reddit.skip reason=no_credentials")
        return None
    try:
        r = requests.post(
            _TOKEN_URL,
            auth=(cid, secret),
            data={"grant_type": "password", "username": user, "password": pw},
            headers={"User-Agent": ua},
            timeout=30,
        )
        if r.status_code >= 400:
            log.warning("reddit.token err=status_%s body=%s", r.status_code, r.text[:300])
            return None
        return r.json().get("access_token")
    except Exception as exc:
        log.warning("reddit.token err=%s", exc)
        return None


def post(payload: PostPayload) -> None:
    if not settings.reddit.allowed_subs:
        log.info("reddit.skip reason=no_allowed_subs")
        return
    if not _can_post():
        return
    ua = os.getenv("REDDIT_USER_AGENT") or "openclaw/1.0"
    token = _access_token(ua)
    if not token:
        return

    title = _clean_title(payload.title)
    target_url = utm_url(payload.url, source="reddit")
    body = rewrite(payload.title, payload.excerpt, channel="reddit", url=target_url)
    body = f"{body}\n\nSource: {target_url}"

    headers = {"Authorization": f"bearer {token}", "User-Agent": ua}
    posted_anywhere = False
    for sub in settings.reddit.allowed_subs:
        try:
            r = requests.post(
                _SUBMIT_URL,
                headers=headers,
                data={"sr": sub, "kind": "self", "title": title, "text": body[:39000], "api_type": "json"},
                timeout=30,
            )
            errors = []
            if r.status_code < 400:
                try:
                    errors = r.json().get("json", {}).get("errors", [])
                except Exception:
                    errors = []
            if r.status_code < 400 and not errors:
                log.info("reddit.post ok sub=%s", sub)
                _record_post(sub, target_url, r.text[:500])
                posted_anywhere = True
            else:
                log.warning("reddit.post sub=%s err=status_%s errors=%s body=%s", sub, r.status_code, errors, r.text[:300])
        except Exception as exc:
            log.warning("reddit.post sub=%s err=%s", sub, exc)

    if not posted_anywhere:
        log.info("reddit.post no_subs_succeeded")
