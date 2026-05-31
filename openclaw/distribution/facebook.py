from __future__ import annotations

import os
from typing import Optional

import requests

from ..logging_utils import log
from .base import PostPayload

API = "https://graph.facebook.com/v25.0"


def page_access_token(page: str, user_token: str) -> Optional[str]:
    """Exchange the user/system token for a Page access token.

    Publishing to a Page (feed, reels) requires a Page token, not the
    raw user token — even when the user token already has
    pages_manage_posts.
    """
    try:
        resp = requests.get(
            f"{API}/{page}",
            params={"fields": "access_token", "access_token": user_token},
            timeout=30,
        )
        if resp.status_code >= 400:
            log.warning("facebook.page_token err=status_%s body=%s", resp.status_code, resp.text[:300])
            return None
        return resp.json().get("access_token")
    except Exception as exc:
        log.warning("facebook.page_token err=%s", exc)
        return None


def _post_native(payload: PostPayload) -> bool:
    page = os.getenv("FACEBOOK_PAGE_ID")
    token = os.getenv("FACEBOOK_TOKEN")
    if not (page and token):
        log.info("facebook.skip reason=no_credentials")
        return False
    page_token = page_access_token(page, token) or token
    try:
        resp = requests.post(
            f"{API}/{page}/feed",
            data={"message": payload.social_text, "link": payload.url, "access_token": page_token},
            timeout=30,
        )
        if resp.status_code >= 400:
            log.warning("facebook.post err=status_%s body=%s", resp.status_code, resp.text[:300])
            return False
        log.info("facebook.post ok url=%s id=%s", payload.url, resp.json().get("id"))
        return True
    except Exception as exc:
        log.warning("facebook.post err=%s", exc)
        return False


def post(payload: PostPayload) -> None:
    # Direct Facebook Graph API only (Composio path removed per config).
    _post_native(payload)
