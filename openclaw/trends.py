"""Trending topic discovery via DuckDuckGo News."""
from __future__ import annotations

import random
from typing import Optional

from ddgs import DDGS

from .logging_utils import log


def fetch_trending_topic(category: str, max_results: int = 10) -> str:
    """Return a trending news headline related to `category`, falling back
    to the category name itself if the search fails or yields nothing."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query=category, max_results=max_results))
        if results:
            picked = random.choice(results)["title"]
            log.info("trends.fetch hit category=%s topic=%r", category, picked)
            return picked
    except Exception as exc:
        log.warning("trends.fetch failed category=%s err=%s", category, exc)
    log.info("trends.fetch miss category=%s using_category_name=true", category)
    return category
