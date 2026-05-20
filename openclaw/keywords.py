"""Evergreen long-tail keyword discovery — replaces news-chasing trends.py."""
from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import Iterable, List, Optional

import requests

from .config import DATA_DIR, settings
from .logging_utils import log
from .topic_filter import is_safe_topic

POOL_FILE = DATA_DIR / "keyword_pool.json"
USED_FILE = DATA_DIR / "keyword_used.json"

# Hand-curated seed patterns that historically rank well as evergreen
# long-tail. The {} is replaced with the category name.
SEED_TEMPLATES: list[str] = [
    "what is {}",
    "how does {} work",
    "how to use {}",
    "how to learn {}",
    "best free {} tools 2026",
    "{} for beginners",
    "{} vs",
    "{} explained",
    "common {} mistakes",
    "{} tutorial step by step",
    "is {} worth it",
    "{} use cases",
    "{} best practices",
    "{} examples",
    "future of {}",
    "{} cheat sheet",
    "{} interview questions",
    "self host {}",
    "{} comparison",
    "how much does {} cost",
]

# Per-category overrides for any category whose name is not a great
# search query as-is (e.g. trading nicknames). Add more as needed.
CATEGORY_ALIASES: dict[str, str] = {
    "Defi": "decentralized finance",
    "Entry": "trade entry strategy",
    "Indicators": "trading indicators",
    "Pattern": "chart patterns",
    "Fundamental": "fundamental analysis",
    "Candle": "candlestick patterns",
    "Quantitative AI": "quantitative trading AI",
}


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _ddg_suggest(query: str, region: str = "wt-wt", timeout: int = 8) -> list[str]:
    """DuckDuckGo autosuggest. Returns up to 8 long-tail phrasings."""
    try:
        r = requests.get(
            "https://duckduckgo.com/ac/",
            params={"q": query, "kl": region, "type": "list"},
            headers={"User-Agent": "Mozilla/5.0 OpenClawKeywords/0.2"},
            timeout=timeout,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        # Response shape: [{"phrase": "..."}], ...] OR ["q", ["sugg1", ...]]
        out: list[str] = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "phrase" in item:
                    out.append(item["phrase"])
                elif isinstance(item, list):
                    out.extend(s for s in item if isinstance(s, str))
                elif isinstance(item, str):
                    out.append(item)
        return out[:10]
    except Exception as exc:
        log.debug("kw.ddg_err q=%r err=%s", query, exc)
        return []


def _youtube_suggest(query: str, timeout: int = 8) -> list[str]:
    """YouTube autosuggest. Hits the public google complete endpoint."""
    try:
        r = requests.get(
            "https://suggestqueries.google.com/complete/search",
            params={"client": "youtube", "ds": "yt", "q": query},
            headers={"User-Agent": "Mozilla/5.0 OpenClawKeywords/0.2"},
            timeout=timeout,
        )
        if r.status_code != 200:
            return []
        # Format: ['query', [['suggestion', ...], ...], ...]
        # Body is JSON-ish but wrapped, response.text starts with "window.google..."
        # Newer endpoint returns plain JSON though.
        text = r.text.strip()
        if text.startswith("window."):
            text = text[text.index("(") + 1 : text.rindex(")")]
        data = json.loads(text)
        if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
            return [s[0] if isinstance(s, list) else s for s in data[1]][:10]
    except Exception as exc:
        log.debug("kw.yt_err q=%r err=%s", query, exc)
    return []


def _expand_category(category_name: str) -> list[str]:
    """Build a candidate keyword list for a category: seeds + autosuggest."""
    base = CATEGORY_ALIASES.get(category_name, category_name)
    candidates: set[str] = set()

    # Seed templates
    for tmpl in SEED_TEMPLATES:
        candidates.add(_normalize(tmpl.format(base)))

    # Expand a subset via autosuggest (rate-limit friendly: only the top 4 seeds)
    for tmpl in SEED_TEMPLATES[:4]:
        q = tmpl.format(base)
        for sugg in _ddg_suggest(q):
            candidates.add(_normalize(sugg))
        for sugg in _youtube_suggest(q):
            candidates.add(_normalize(sugg))
        time.sleep(0.4)  # polite pause

    # Filter through the safety net
    safe = [c for c in candidates if is_safe_topic(c)[0]]
    log.info("kw.expand category=%r candidates=%d safe=%d",
             category_name, len(candidates), len(safe))
    return sorted(safe)


def load_pool() -> dict:
    if POOL_FILE.exists():
        try:
            return json.loads(POOL_FILE.read_text())
        except Exception:
            pass
    return {}


def save_pool(pool: dict) -> None:
    POOL_FILE.parent.mkdir(parents=True, exist_ok=True)
    POOL_FILE.write_text(json.dumps(pool, indent=2, sort_keys=True))


def load_used() -> set[str]:
    if USED_FILE.exists():
        try:
            return set(json.loads(USED_FILE.read_text()))
        except Exception:
            pass
    return set()


def save_used(used: set[str]) -> None:
    USED_FILE.parent.mkdir(parents=True, exist_ok=True)
    USED_FILE.write_text(json.dumps(sorted(used), indent=2))


def refresh_pool(categories: Iterable[dict], force: bool = False) -> dict:
    """Rebuild the keyword pool for every category. Safe to call repeatedly."""
    pool = {} if force else load_pool()
    for cat in categories:
        name = cat["name"]
        if name in pool and len(pool[name]) >= 30 and not force:
            continue
        pool[name] = _expand_category(name)
    save_pool(pool)
    return pool


def pick_topic(category_name: str, existing_titles: Optional[List[str]] = None) -> str:
    """Pick one fresh keyword for the category. Falls back to a synthetic
    'what is X' if the pool is empty (which then still passes the filter)."""
    pool = load_pool()
    used = load_used()
    existing_normalized = {_normalize(t) for t in (existing_titles or [])}

    candidates = pool.get(category_name) or []
    candidates = [c for c in candidates
                  if c not in used and c not in existing_normalized
                  and is_safe_topic(c)[0]]

    if not candidates:
        log.warning("kw.pool_empty category=%s — refreshing", category_name)
        pool[category_name] = _expand_category(category_name)
        save_pool(pool)
        candidates = [c for c in pool[category_name]
                      if c not in used and c not in existing_normalized]

    if not candidates:
        fallback = f"what is {CATEGORY_ALIASES.get(category_name, category_name).lower()}"
        log.warning("kw.fallback category=%s topic=%r", category_name, fallback)
        return fallback

    topic = random.choice(candidates)
    used.add(topic)
    save_used(used)
    log.info("kw.pick category=%s topic=%r pool=%d", category_name, topic, len(candidates))
    return topic


def fetch_trending_topic(category_name: str) -> str:
    """Drop-in replacement for the legacy trends.fetch_trending_topic."""
    return pick_topic(category_name)
