from __future__ import annotations

import os

import requests

from ..logging_utils import log
from .base import PostPayload


def post(payload: PostPayload) -> None:
    page = os.getenv("FACEBOOK_PAGE_ID")
    token = os.getenv("FACEBOOK_TOKEN")
    if not (page and token):
        log.info("facebook.skip reason=no_credentials")
        return
    try:
        requests.post(
            f"https://graph.facebook.com/v25.0/{page}/feed",
            data={"message": payload.social_text, "link": payload.url, "access_token": token},
            timeout=30,
        )
        log.info("facebook.post ok url=%s", payload.url)
    except Exception as exc:
        log.warning("facebook.post err=%s", exc)
