from __future__ import annotations

import os

import requests

from ..composio_client import available as composio_available
from ..config import settings
from ..logging_utils import log
from . import composio_facebook
from .base import PostPayload


def post(payload: PostPayload) -> None:
    if composio_available() and settings.composio.facebook_account_id:
        return composio_facebook.post(payload)
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
