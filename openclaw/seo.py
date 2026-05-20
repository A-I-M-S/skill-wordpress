"""SEO helpers: deduping, internal linking, E-E-A-T enrichment, schema."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from .config import settings
from .logging_utils import log


def _normalize_title(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _token_jaccard(a: str, b: str) -> float:
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def is_duplicate_title(
    candidate: str, existing: Iterable[str], threshold: Optional[float] = None
) -> bool:
    """Return True if candidate is too similar to any existing title.

    Catches three duplicate patterns common to autoblogs:
      1. SequenceMatcher ratio >= threshold (near-identical strings).
      2. One title is a substring/prefix of the other (the "-2" slug pattern).
      3. Token-set Jaccard >= threshold (same words, reshuffled).
    """
    thresh = threshold if threshold is not None else settings.publishing.title_similarity_threshold
    norm_cand = _normalize_title(candidate)
    if not norm_cand:
        return False
    for other in existing:
        if not other:
            continue
        norm_other = _normalize_title(other)
        if not norm_other:
            continue
        # 2. substring / prefix containment
        shorter, longer = sorted((norm_cand, norm_other), key=len)
        if shorter and shorter in longer and len(shorter) / max(len(longer), 1) >= 0.5:
            log.info("seo.dedup HIT mode=substring cand=%r vs=%r", candidate, other)
            return True
        # 1. character-level similarity
        ratio = SequenceMatcher(None, norm_cand, norm_other).ratio()
        if ratio >= thresh:
            log.info("seo.dedup HIT mode=ratio score=%.2f cand=%r vs=%r", ratio, candidate, other)
            return True
        # 3. token-set similarity
        jacc = _token_jaccard(norm_cand, norm_other)
        if jacc >= thresh:
            log.info("seo.dedup HIT mode=jaccard score=%.2f cand=%r vs=%r", jacc, candidate, other)
            return True
    return False


def inject_internal_links(html: str, related: Sequence[dict], max_links: int = 3) -> str:
    """Append a Related Reading block linking to other in-niche posts.
    `related` items must have `title` and `link` keys (WP REST shape)."""
    if not related:
        return html
    chosen = related[:max_links]
    items = "\n".join(
        f'<li><a href="{post["link"]}" rel="bookmark">{post["title"]}</a></li>'
        for post in chosen
    )
    block = (
        "\n<h3>Related reading on InsightGinie</h3>\n"
        f"<ul>\n{items}\n</ul>\n"
    )
    return html + block


def inject_author_block(html: str, post_url_hint: Optional[str] = None) -> str:
    """Append a small E-E-A-T review block at the end of the article."""
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    block = (
        f'\n<p class="ig-review-block"><em>Reviewed by '
        f'<a href="{settings.publishing.author_url}" rel="author">'
        f"{settings.publishing.author_name}</a> on {today}. "
        f"InsightGinie publishes practitioner-led analysis on AI, "
        f"automation, and quantitative trading.</em></p>\n"
    )
    return html + block


def build_article_schema(
    title: str,
    excerpt: str,
    url: str,
    image_url: Optional[str],
    published_iso: Optional[str] = None,
) -> str:
    """Return a <script type='application/ld+json'> block for Article schema."""
    published = published_iso or datetime.now(timezone.utc).isoformat()
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title[:110],
        "description": excerpt,
        "url": url,
        "datePublished": published,
        "dateModified": published,
        "author": {
            "@type": "Person",
            "name": settings.publishing.author_name,
            "url": settings.publishing.author_url,
        },
        "publisher": {
            "@type": "Organization",
            "name": "InsightGinie",
            "url": f"https://{settings.wp.host}",
        },
    }
    if image_url:
        data["image"] = image_url
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


_SLUG_RE = re.compile(r"[^a-z0-9-]")


def slugify(text: str, max_len: int = 60) -> str:
    s = text.lower().strip().replace(" ", "-")
    s = _SLUG_RE.sub("", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:max_len] or "post"


def primary_keyword(tags: Sequence[str], fallback: str) -> str:
    return (tags[0] if tags else fallback).strip()


def load_recent_titles(state_file: Path, lookback: int = 200) -> List[str]:
    if not state_file.exists():
        return []
    try:
        data = json.loads(state_file.read_text())
        return [item["title"] for item in data.get("recent_posts", [])[-lookback:]]
    except Exception as exc:
        log.warning("seo.state_read err=%s", exc)
        return []
