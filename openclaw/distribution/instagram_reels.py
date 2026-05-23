"""Instagram Reels via Meta Graph API.

Two-step async flow:
  1. POST /{ig_user_id}/media     media_type=REELS, video_url, caption
     -> returns container_id; status starts as IN_PROGRESS
  2. Poll GET /{container_id}?fields=status_code  until FINISHED
  3. POST /{ig_user_id}/media_publish creation_id={container_id}
     -> returns the live IG media id

Auth: needs an Instagram Business or Creator account linked to a FB Page.
The Page access token (same one used for Facebook posts) is used here,
just with `instagram_content_publish` + `instagram_basic` scopes added.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import requests

from ..logging_utils import log
from .base import PostPayload
from .video_hosting import host_video

API = "https://graph.facebook.com/v25.0"
MAX_POLL_S = 180
POLL_INTERVAL = 5


def post_video(payload: PostPayload, video_path: Path) -> Optional[str]:
    ig_user = os.getenv("INSTAGRAM_USER_ID")
    token = os.getenv("INSTAGRAM_TOKEN") or os.getenv("FACEBOOK_TOKEN")
    if not (ig_user and token):
        log.info("instagram_reels.skip reason=no_credentials")
        return None

    video_url = host_video(video_path)
    if not video_url:
        log.warning("instagram_reels.skip reason=video_hosting_failed")
        return None

    caption = _build_caption(payload)
    try:
        r = requests.post(
            f"{API}/{ig_user}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": token,
                "share_to_feed": "true",
            },
            timeout=30,
        )
        r.raise_for_status()
        container_id = r.json().get("id")
        if not container_id:
            log.warning("instagram_reels.no_container body=%s", r.text[:300])
            return None

        # Poll until container is FINISHED (Meta needs to ingest the mp4)
        deadline = time.time() + MAX_POLL_S
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            s = requests.get(
                f"{API}/{container_id}",
                params={"fields": "status_code", "access_token": token},
                timeout=20,
            ).json()
            code = s.get("status_code")
            if code == "FINISHED":
                break
            if code in {"ERROR", "EXPIRED"}:
                log.warning("instagram_reels.ingest_failed code=%s detail=%s", code, s)
                return None
        else:
            log.warning("instagram_reels.ingest_timeout container=%s", container_id)
            return None

        # Publish
        p = requests.post(
            f"{API}/{ig_user}/media_publish",
            data={"creation_id": container_id, "access_token": token},
            timeout=30,
        )
        p.raise_for_status()
        media_id = p.json().get("id")
        url = f"https://www.instagram.com/reel/{media_id}/" if media_id else None
        log.info("instagram_reels.posted url=%s wp_url=%s", url or "(no id)", payload.url)
        return url
    except Exception as exc:
        log.warning("instagram_reels.err=%s", exc)
        return None


def _build_caption(payload: PostPayload) -> str:
    base = (payload.social_text or payload.title or "").strip()
    tail = f"\n\nRead more: {payload.url}\n\n#AI #Tech"
    budget = 2200 - len(tail)  # IG hard limit is 2200
    if len(base) > budget:
        base = base[: budget - 1].rstrip() + "…"
    return base + tail
