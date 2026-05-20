"""Search-engine indexing pings."""
from __future__ import annotations

from typing import Iterable, List

import requests

from .config import settings
from .logging_utils import log


def submit_indexnow(urls: Iterable[str]) -> None:
    url_list: List[str] = [u for u in urls if u]
    if not url_list or not settings.indexnow_key:
        return
    try:
        requests.post(
            "https://api.indexnow.org/indexnow",
            json={
                "host": settings.wp.host,
                "key": settings.indexnow_key,
                "urlList": url_list,
            },
            timeout=15,
        )
        log.info("indexnow.submit count=%d", len(url_list))
    except Exception as exc:
        log.warning("indexnow.submit err=%s", exc)


def submit_bing(urls: Iterable[str]) -> None:
    """Bing Webmaster Tools URL submission API (free, separate from IndexNow)."""
    url_list = [u for u in urls if u]
    if not url_list or not settings.bing_api_key:
        return
    try:
        requests.post(
            f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlbatch?apikey={settings.bing_api_key}",
            json={"siteUrl": f"https://{settings.wp.host}", "urlList": url_list},
            timeout=15,
        )
        log.info("bing.submit count=%d", len(url_list))
    except Exception as exc:
        log.warning("bing.submit err=%s", exc)
