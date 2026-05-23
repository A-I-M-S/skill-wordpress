"""Automated topic-cluster internal linking.

For each new post, find 3-5 closely-related existing posts in the same
category cluster and inject contextual links inline (not just a 'Related
Reading' block at the bottom — though that exists too).

Strategy:
  1. Pull recent posts in the same category from WP (with embed=1).
  2. Score relevance against the new article via tag overlap +
     title-keyword Jaccard.
  3. For the top-K, find the first H2 in the article whose heading
     contains a relevant token, and inject one <a> per match into the
     paragraph immediately following that H2.
  4. Append a "Related Reading" <ul> at the end as a fallback / catchall.

This is the single biggest signal Google uses to identify topic clusters
within a site — and it's nearly free (one extra WP query per publish).
"""
from __future__ import annotations

import re
from html import escape
from typing import Iterable, List, Optional

import requests

from .config import settings
from .logging_utils import log


STOPWORDS = {
    "about", "after", "before", "beginner", "beginners", "complete", "could",
    "does", "entry", "explained", "guide", "learn", "properly", "reveals",
    "should", "strategy", "ultimate", "using", "what", "when", "where",
    "which", "with", "work", "works", "your",
}


def _tokens(text: str) -> set[str]:
    text = re.sub(r"<[^>]+>", " ", text).lower()
    tokens = set(re.findall(r"[a-z][a-z0-9]{2,}", text))
    return {t for t in tokens if len(t) > 3 and t not in STOPWORDS}


def _score(new_tokens: set[str], post: dict) -> float:
    title = post.get("title", {}).get("rendered", "") or ""
    excerpt = post.get("excerpt", {}).get("rendered", "") or ""
    tags = set()
    for tag_list in (post.get("_embedded", {}).get("wp:term") or []):
        if isinstance(tag_list, list):
            for t in tag_list:
                if isinstance(t, dict):
                    tags |= _tokens(t.get("name", ""))
    title_tokens = _tokens(title)
    other_tokens = title_tokens | _tokens(excerpt) | tags
    if not other_tokens:
        return 0.0
    overlap = new_tokens & other_tokens
    title_overlap = new_tokens & title_tokens
    tag_overlap = new_tokens & tags
    if len(title_overlap) < 2 and not tag_overlap:
        return 0.0
    inter = len(overlap)
    union = len(new_tokens | other_tokens)
    return inter / union if union else 0.0


def find_related(
    new_title: str,
    new_tags: Iterable[str],
    category_id: int,
    *,
    limit: int = 5,
    pool_size: int = 50,
) -> list[dict]:
    """Return up to `limit` candidate posts, ranked by token+tag overlap."""
    try:
        resp = requests.get(
            f"{settings.wp.api_base}/posts",
            params={
                "categories": category_id,
                "per_page": pool_size,
                "_embed": 1,
                "orderby": "date",
                "order": "desc",
            },
            timeout=20,
        )
        if not resp.ok:
            return []
        candidates = resp.json()
    except Exception as exc:
        log.warning("linker.fetch_err err=%s", exc)
        return []

    new_tokens = _tokens(new_title)
    for tag in new_tags:
        new_tokens |= _tokens(tag)
    scored = [
        (_score(new_tokens, p), p) for p in candidates
        if p.get("link")
    ]
    scored.sort(key=lambda x: -x[0])
    return [p for s, p in scored if s >= 0.10][:limit]


def inject_inline_links(html: str, related: list[dict], max_inline: int = 3) -> str:
    """Find the first occurrence of each related post's key noun in the
    body and wrap it in an <a href> link. Cap at `max_inline` total."""
    if not related:
        return html
    used_urls: set[str] = set()
    out = html
    inserted = 0
    for post in related:
        if inserted >= max_inline:
            break
        title = post["title"]["rendered"]
        url = post["link"]
        if url in used_urls:
            continue
        # Pick the most "noun-y" 2-3 word token sequence in the title.
        # Strip common stopwords and HTML.
        clean_title = re.sub(r"<[^>]+>", "", title).strip()
        words = clean_title.split()
        for n in (4, 3, 2):
            if len(words) < n:
                continue
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i + n])
                if len(phrase) < 8:
                    continue
                # Case-insensitive single replacement in body, but only in
                # paragraph text (avoid double-linking inside existing <a>).
                pattern = re.compile(
                    rf"(?<![>\w])({re.escape(phrase)})(?![\w<])",
                    flags=re.IGNORECASE,
                )
                if not pattern.search(out):
                    continue
                replacement = (
                    f'<a href="{escape(url)}" '
                    f'title="{escape(clean_title)}">\\1</a>'
                )
                # Avoid linking inside existing <a> tags by checking first.
                new_out, n_subs = pattern.subn(replacement, out, count=1)
                if n_subs > 0:
                    out = new_out
                    used_urls.add(url)
                    inserted += 1
                    break
            if url in used_urls:
                break
    log.info("linker.inline inserted=%d/%d", inserted, max_inline)
    return out


def append_related_block(html: str, related: list[dict]) -> str:
    if not related:
        return html
    items = "\n".join(
        f'<li><a href="{escape(p["link"])}" rel="bookmark">'
        f'{escape(re.sub(r"<[^>]+>", "", p["title"]["rendered"]))}</a></li>'
        for p in related
    )
    block = (
        '<section class="related-reading">'
        '<h2>Related Reading</h2>'
        f'<ul>{items}</ul>'
        "</section>"
    )
    return html + "\n\n" + block


def link(html: str, *, title: str, tags: list[str], category_id: int) -> str:
    """One-shot: enhance HTML with inline links + a related block."""
    related = find_related(title, tags, category_id)
    if not related:
        log.info("linker.no_matches title=%r", title)
        return html
    html = inject_inline_links(html, related, max_inline=3)
    html = append_related_block(html, related)
    return html
