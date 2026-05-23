"""Threads video post — Meta's text-network video upload.

Same two-step container/publish pattern as Instagram:
  1. POST /{threads_id}/threads   media_type=VIDEO, video_url, text
  2. Wait for `status` to reach FINISHED (poll the container id)
  3. POST /{threads_id}/threads_publish  creation_id=...

Reuses the same THREADS_TOKEN as the text distributor.
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

API = "https://graph.threads.net/v1.0"
MAX_POLL_S = 180
POLL_INTERVAL = 5


def post_video(payload: PostPayload, video_path: Path) -> Optional[str]:
    threads_id = os.getenv("THREADS_ID")
    token = os.getenv("THREADS_TOKEN")
    if not (threads_id and token):
        log.info("threads_video.skip reason=no_credentials")
        return None

    video_url = host_video(video_path)
    if not video_url:
        log.warning("threads_video.skip reason=video_hosting_failed")
        return None

    text = _build_text(payload)
    try:
        r = requests.post(
            f"{API}/{threads_id}/threads",
            data={
                "media_type": "VIDEO",
                "video_url": video_url,
                "text": text,
                "access_token": token,
            },
            timeout=30,
        )
        r.raise_for_status()
        container_id = r.json().get("id")
        if not container_id:
            log.warning("threads_video.no_container body=%s", r.text[:300])
            return None

        # Poll
        deadline = time.time() + MAX_POLL_S
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            s = requests.get(
                f"{API}/{container_id}",
                params={"fields": "status", "access_token": token},
                timeout=20,
            ).json()
            status = (s.get("status") or "").upper()
            if status == "FINISHED":
                break
            if status in {"ERROR", "EXPIRED"}:
                log.warning("threads_video.ingest_failed status=%s detail=%s", status, s)
                return None
        else:
            log.warning("threads_video.ingest_timeout container=%s", container_id)
            return None

        # Publish
        p = requests.post(
            f"{API}/{threads_id}/threads_publish",
            data={"creation_id": container_id, "access_token": token},
            timeout=30,
        )
        p.raise_for_status()
        media_id = p.json().get("id")
        log.info("threads_video.posted id=%s wp_url=%s", media_id, payload.url)
        return media_id
    except Exception as exc:
        log.warning("threads_video.err=%s", exc)
        return None


def _build_text(payload: PostPayload) -> str:
    base = (payload.social_text or payload.title or "").strip()
    return f"{base}\n\n{payload.url}"[:500]  # Threads hard limit
