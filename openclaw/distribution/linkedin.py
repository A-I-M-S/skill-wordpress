from __future__ import annotations

import os
from typing import Optional

import requests

from ..logging_utils import log
from .base import PostPayload

API = "https://api.linkedin.com/v2/ugcPosts"


def _post_native(payload: PostPayload) -> Optional[str]:
    token = os.getenv("LINKEDIN_TOKEN")
    author = os.getenv("LINKEDIN_AUTHOR") or os.getenv("LINKEDIN_AUTHOR_URN")
    if not (token and author):
        log.info("linkedin.skip reason=no_credentials")
        return None
    try:
        resp = requests.post(
            API,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json={
                "author": author,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": payload.social_text},
                        "shareMediaCategory": "ARTICLE",
                        "media": [
                            {
                                "status": "READY",
                                "originalUrl": payload.url,
                                "title": {"text": payload.title[:200]},
                                "description": {"text": payload.excerpt[:256]},
                            }
                        ],
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            log.warning("linkedin.post err=status_%s body=%s", resp.status_code, resp.text[:300])
            return None
        post_id = resp.headers.get("x-restli-id") or resp.json().get("id")
        log.info("linkedin.post ok url=%s id=%s", payload.url, post_id)
        return post_id
    except Exception as exc:
        log.warning("linkedin.post err=%s", exc)
        return None


def post(payload: PostPayload) -> None:
    # Direct LinkedIn API only (Composio path removed).
    _post_native(payload)
