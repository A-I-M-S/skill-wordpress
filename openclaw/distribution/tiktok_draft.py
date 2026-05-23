"""TikTok via Content Posting API — DRAFT or DIRECT-POST mode.

Two modes, switched by env var TIKTOK_DIRECT_POST:

  DRAFT MODE (TIKTOK_DIRECT_POST=false)
    Endpoint: /v2/post/publish/inbox/video/init/
    Video lands in the user's TikTok Inbox; user taps "Post" to publish.
    Works with any unaudited client_key.

  DIRECT-POST MODE (TIKTOK_DIRECT_POST=true)  — what AC's app is being
    audited for. Endpoint: /v2/post/publish/video/init/
    Posts immediately to the user's profile.

    IMPORTANT: until the app is audited, TikTok forces privacy_level to
    SELF_ONLY (only you can see it). Once audited, set TIKTOK_PRIVACY
    to PUBLIC_TO_EVERYONE (or MUTUAL_FOLLOW_FRIENDS / FOLLOWER_OF_CREATOR)
    in .env and posts will be truly public.

Auth: oauth2 user access token. For draft only: `video.upload` scope.
For direct post: also `video.publish` scope.
Docs: https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
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


INBOX_INIT = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
DIRECT_INIT = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def _direct_post_payload(payload: PostPayload, video_url: str) -> dict:
    return {
        "post_info": {
            "title": payload.title[:150],
            "privacy_level": os.getenv("TIKTOK_PRIVACY", "SELF_ONLY"),
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url,
        },
    }


def _draft_payload(video_url: str) -> dict:
    return {
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url,
        },
    }


def post_video(payload: PostPayload, mp4_path: Path) -> Optional[str]:
    token = os.getenv("TIKTOK_ACCESS_TOKEN")
    if not token:
        log.warning("tiktok.skip reason=no_TIKTOK_ACCESS_TOKEN")
        return None
    if not mp4_path or not Path(mp4_path).exists():
        log.warning("tiktok.skip reason=no_video path=%s", mp4_path)
        return None

    direct = os.getenv("TIKTOK_DIRECT_POST", "false").lower() == "true"
    mode = "direct_post" if direct else "draft"
    privacy = os.getenv("TIKTOK_PRIVACY", "SELF_ONLY") if direct else "n/a"

    try:
        video_url = host_video(mp4_path, slug=Path(mp4_path).stem)
        if not video_url:
            log.warning("tiktok.skip reason=video_host_failed")
            return None
        log.info("tiktok.start mode=%s privacy=%s video_url=%s",
                 mode, privacy, video_url)

        endpoint = DIRECT_INIT if direct else INBOX_INIT
        body = _direct_post_payload(payload, video_url) if direct else _draft_payload(video_url)

        r = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json=body,
            timeout=30,
        )
        if r.status_code >= 400:
            log.warning("tiktok.init_failed status=%d body=%s",
                        r.status_code, r.text[:300])
            return None
        data = r.json().get("data", {})
        publish_id = data.get("publish_id")
        if not publish_id:
            log.warning("tiktok.init_no_id resp=%s", r.text[:200])
            return None
        log.info("tiktok.init ok publish_id=%s", publish_id)

        # Poll status for up to 60s — TikTok usually finishes within 20s.
        for _ in range(12):
            time.sleep(5)
            sr = requests.post(
                STATUS,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                json={"publish_id": publish_id},
                timeout=20,
            )
            if sr.status_code >= 400:
                log.warning("tiktok.status_err status=%d body=%s",
                            sr.status_code, sr.text[:200])
                continue
            status = (sr.json().get("data") or {}).get("status", "")
            log.info("tiktok.status %s", status)
            if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                # On direct-post, the SDK returns the publicly-shared post id.
                publicaly_available_post_id = (sr.json().get("data") or {}).get(
                    "publicaly_available_post_id"
                )
                if publicaly_available_post_id:
                    url = f"https://www.tiktok.com/@me/video/{publicaly_available_post_id[0]}"
                else:
                    url = f"tiktok:publish_id:{publish_id}"
                log.info("tiktok.done mode=%s url=%s", mode, url)
                return url
            if status in ("FAILED", "EXPIRED"):
                log.warning("tiktok.terminal status=%s body=%s",
                            status, sr.text[:200])
                return None

        log.warning("tiktok.timeout publish_id=%s", publish_id)
        return None
    except Exception as exc:
        log.warning("tiktok.exception mode=%s err=%s", mode, exc)
        return None


# Backward-compat alias for older imports.
post = post_video
