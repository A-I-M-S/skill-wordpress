from __future__ import annotations

import os

import requests

from ..logging_utils import log
from .base import PostPayload


def post(payload: PostPayload) -> None:
    token = os.getenv("LINKEDIN_TOKEN")
    author = os.getenv("LINKEDIN_AUTHOR")
    if not (token and author):
        log.info("linkedin.skip reason=no_credentials")
        return
    try:
        requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
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
        log.info("linkedin.post ok url=%s", payload.url)
    except Exception as exc:
        log.warning("linkedin.post err=%s", exc)
