"""Facebook Reels via Graph API (resumable upload).

Three-step flow:
  1. POST /{page_id}/video_reels  upload_phase=start   -> get video_id + upload_url
  2. POST {upload_url}  with file_url=... (or binary)  -> uploads the bytes
  3. POST /{page_id}/video_reels  upload_phase=finish, video_id, description,
                                  video_state=PUBLISHED

Uses the same page token already configured for Facebook text posts,
just needs `pages_manage_posts` + `pages_read_engagement` scopes (you
likely already have these for normal feed posting).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import requests

from ..logging_utils import log
from .base import PostPayload
from .facebook import page_access_token
from .video_hosting import host_video

API = "https://graph.facebook.com/v25.0"


def post_video(payload: PostPayload, video_path: Path) -> Optional[str]:
    page = os.getenv("FACEBOOK_PAGE_ID")
    token = os.getenv("FACEBOOK_TOKEN")
    if not (page and token):
        log.info("facebook_reels.skip reason=no_credentials")
        return None

    page_token = page_access_token(page, token) or token

    video_url = host_video(video_path)
    if not video_url:
        log.warning("facebook_reels.skip reason=video_hosting_failed")
        return None

    description = _build_description(payload)
    try:
        # Phase 1 — start
        r = requests.post(
            f"{API}/{page}/video_reels",
            data={"upload_phase": "start", "access_token": page_token},
            timeout=30,
        )
        r.raise_for_status()
        start = r.json()
        video_id = start.get("video_id")
        upload_url = start.get("upload_url")
        if not (video_id and upload_url):
            log.warning("facebook_reels.start_failed body=%s", r.text[:300])
            return None

        # Phase 2 — file_url upload (Meta fetches from our WP CDN)
        u = requests.post(
            upload_url,
            headers={"Authorization": f"OAuth {page_token}", "file_url": video_url},
            timeout=60,
        )
        u.raise_for_status()
        if not u.json().get("success", True):
            log.warning("facebook_reels.upload_failed body=%s", u.text[:300])
            return None

        # Phase 3 — finish & publish
        f = requests.post(
            f"{API}/{page}/video_reels",
            data={
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": description,
                "access_token": page_token,
            },
            timeout=30,
        )
        f.raise_for_status()
        url = f"https://www.facebook.com/reel/{video_id}"
        log.info("facebook_reels.posted url=%s wp_url=%s", url, payload.url)
        return url
    except Exception as exc:
        log.warning("facebook_reels.err=%s", exc)
        return None


def _build_description(payload: PostPayload) -> str:
    base = (payload.social_text or payload.title or "").strip()
    return f"{base}\n\nFull article: {payload.url}"[:2200]
