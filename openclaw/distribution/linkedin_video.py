"""LinkedIn native video post via the Posts API + Assets API.

Three-step flow:
  1. POST /rest/videos?action=initializeUpload  -> video URN + uploadInstructions
  2. PUT each upload-instruction URL with the file bytes -> etag per part
  3. POST /rest/videos?action=finalizeUpload  -> video is ingested
  4. POST /rest/posts  with media{ id: video URN, ... }  -> live post

LinkedIn uses the same OAuth token already configured for text posts.
Required scope: w_member_social (you already have it).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import requests

from ..logging_utils import log
from .base import PostPayload

API = "https://api.linkedin.com"
HEADERS_BASE = {
    "LinkedIn-Version": "202506",
    "X-Restli-Protocol-Version": "2.0.0",
}


def post_video(payload: PostPayload, video_path: Path) -> Optional[str]:
    token = os.getenv("LINKEDIN_TOKEN")
    author = os.getenv("LINKEDIN_AUTHOR")  # urn:li:person:xxx or urn:li:organization:xxx
    if not (token and author):
        log.info("linkedin_video.skip reason=no_credentials")
        return None

    headers = {**HEADERS_BASE, "Authorization": f"Bearer {token}"}
    file_size = video_path.stat().st_size

    try:
        # 1. Initialize
        init = requests.post(
            f"{API}/rest/videos?action=initializeUpload",
            headers={**headers, "Content-Type": "application/json"},
            json={"initializeUploadRequest": {
                "owner": author,
                "fileSizeBytes": file_size,
                "uploadCaptions": False,
                "uploadThumbnail": False,
            }},
            timeout=30,
        )
        init.raise_for_status()
        v = init.json().get("value", {})
        video_urn = v.get("video")
        instructions = v.get("uploadInstructions") or []
        if not (video_urn and instructions):
            log.warning("linkedin_video.init_failed body=%s", init.text[:300])
            return None

        # 2. Upload parts (LinkedIn returns >=1 part for files >4MB)
        etags = []
        with video_path.open("rb") as fh:
            for instr in instructions:
                url = instr["uploadUrl"]
                first = int(instr["firstByte"])
                last = int(instr["lastByte"])
                fh.seek(first)
                chunk = fh.read(last - first + 1)
                up = requests.put(url, data=chunk, headers={"Authorization": f"Bearer {token}"}, timeout=120)
                up.raise_for_status()
                etags.append(up.headers.get("ETag") or up.headers.get("etag"))

        # 3. Finalize
        fin = requests.post(
            f"{API}/rest/videos?action=finalizeUpload",
            headers={**headers, "Content-Type": "application/json"},
            json={"finalizeUploadRequest": {
                "video": video_urn,
                "uploadToken": "",
                "uploadedPartIds": etags,
            }},
            timeout=30,
        )
        fin.raise_for_status()

        # 4. Create the post
        commentary = _build_commentary(payload)
        post = requests.post(
            f"{API}/rest/posts",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "author": author,
                "commentary": commentary,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "content": {"media": {"id": video_urn, "title": payload.title[:200]}},
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            },
            timeout=30,
        )
        post.raise_for_status()
        post_urn = post.headers.get("x-restli-id") or ""
        log.info("linkedin_video.posted urn=%s wp_url=%s", post_urn, payload.url)
        return post_urn or "ok"
    except Exception as exc:
        log.warning("linkedin_video.err=%s", exc)
        return None


def _build_commentary(payload: PostPayload) -> str:
    base = (payload.social_text or payload.title or "").strip()
    return f"{base}\n\n{payload.url}"[:3000]
