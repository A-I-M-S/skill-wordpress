from __future__ import annotations

import os
import time

import requests

from ..logging_utils import log
from .base import PostPayload


def post(payload: PostPayload) -> None:
    threads_id = os.getenv("THREADS_ID")
    token = os.getenv("THREADS_TOKEN")
    if not (threads_id and token):
        log.info("threads.skip reason=no_credentials")
        return
    try:
        endpoint = f"https://graph.threads.net/v1.0/{threads_id}/threads"
        data = {"text": payload.social_text, "access_token": token}
        if payload.image_url:
            data.update({"media_type": "IMAGE", "image_url": payload.image_url})
        creation = requests.post(endpoint, data=data, timeout=30).json()
        time.sleep(5)
        requests.post(
            f"{endpoint}_publish",
            data={"creation_id": creation.get("id"), "access_token": token},
            timeout=30,
        )
        log.info("threads.post ok url=%s", payload.url)
    except Exception as exc:
        log.warning("threads.post err=%s", exc)
