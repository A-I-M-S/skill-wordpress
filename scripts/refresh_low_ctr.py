"""Refresh existing posts that are 'almost ranking' on Google.

Pulls the top opportunities from GSC (or falls back to recent posts if
GSC isn't configured), then for each one:

  1. Fetches the existing post HTML from WordPress.
  2. LLM rewrites the title + meta description to be more click-worthy
     for the specific query that's bringing in impressions.
  3. LLM appends one new H2 section that targets the query directly.
  4. Re-indexes via IndexNow + Bing.
  5. Distributes via promote.py to social channels.

Run weekly:
    0 5 * * 1 cd /path/to/skill-wordpress && python3 scripts/refresh_low_ctr.py

This is the single highest-ROI traffic move for an 8k-post site, because
it compounds on the impressions you've already earned rather than
betting on brand-new posts to rank.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw.config import settings  # noqa: E402
from openclaw.gsc import top_refresh_candidates, is_available as gsc_available, Opportunity  # noqa: E402
from openclaw.indexing import submit_bing, submit_indexnow  # noqa: E402
from openclaw.llm import LLMClient  # noqa: E402
from openclaw.logging_utils import log  # noqa: E402
from openclaw.wordpress.client import WordPressClient  # noqa: E402


REFRESH_PROMPT = """You are an SEO editor. The article below is currently
getting impressions on Google for the query "{query}" but a low click-through
rate (position {position:.1f}, CTR {ctr_pct:.1f}%). Refresh it to better
serve that specific query.

Return ONLY a JSON object with this exact shape:

{{
  "new_title": "<60-char-max title; the query (or near-paraphrase) early; CTR-optimized>",
  "new_excerpt": "<150-160 char meta description, ends with a soft CTA>",
  "new_section_html": "<one new <h2>...</h2> + 2-3 <p> paragraphs (~250 words) that directly answer the query>"
}}

Article title: {title}
First 2000 chars of body:
{body}

Return ONLY the JSON object."""


def _wp_fallback_candidates(limit: int = 5) -> list[dict]:
    """When GSC isn't configured: pick posts 7-30 days old."""
    from datetime import datetime, timedelta, timezone
    end = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    start = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    resp = requests.get(
        f"{settings.wp.api_base}/posts",
        params={
            "per_page": 50,
            "after": start,
            "before": end,
            "orderby": "date",
            "order": "desc",
        },
        timeout=30,
    )
    if not resp.ok:
        return []
    posts = resp.json()
    return posts[:limit]


def _refresh_one_gsc(opp: Opportunity, wp: WordPressClient, dry_run: bool) -> bool:
    # Look up the WP post by slug
    slug = opp.page.rstrip("/").rsplit("/", 1)[-1]
    r = requests.get(f"{settings.wp.api_base}/posts",
                     params={"slug": slug}, timeout=30)
    if not r.ok or not r.json():
        log.warning("refresh.miss slug=%s", slug)
        return False
    post = r.json()[0]
    return _refresh_post(post, opp.query, opp.position, opp.ctr, wp, dry_run)


def _refresh_post(
    post: dict, query: str, position: float, ctr: float,
    wp: WordPressClient, dry_run: bool,
) -> bool:
    post_id = post["id"]
    title = post["title"]["rendered"]
    body = re.sub(r"<[^>]+>", " ", post["content"]["rendered"])[:2000]

    raw = LLMClient().complete_text(
        REFRESH_PROMPT.format(
            query=query, position=position, ctr_pct=ctr * 100,
            title=title, body=body,
        ),
        max_tokens=1200,
    )
    if not raw:
        log.warning("refresh.llm_empty post_id=%d", post_id)
        return False

    try:
        import json
        data = json.loads(re.sub(r"^```[a-z]*\n|\n```$", "", raw.strip(), flags=re.M))
    except Exception as exc:
        log.warning("refresh.parse_err post_id=%d err=%s", post_id, exc)
        return False

    new_title = (data.get("new_title") or title)[:120]
    new_excerpt = data.get("new_excerpt") or post.get("excerpt", {}).get("rendered", "")
    new_body = (
        post["content"]["rendered"]
        + "\n\n"
        + (data.get("new_section_html") or "")
    )

    if dry_run:
        print(f"\n=== Post {post_id} ({post['link']}) ===")
        print(f"OLD TITLE: {title!r}")
        print(f"NEW TITLE: {new_title!r}")
        print(f"NEW EXCERPT: {new_excerpt!r}")
        print(f"NEW SECTION LEN: {len(data.get('new_section_html', ''))}")
        return True

    update_resp = requests.post(
        f"{settings.wp.api_base}/posts/{post_id}",
        auth=wp.auth,
        json={
            "title": new_title,
            "excerpt": new_excerpt,
            "content": new_body,
        },
        timeout=60,
    )
    if not update_resp.ok:
        log.warning("refresh.update_err post_id=%d status=%d body=%s",
                    post_id, update_resp.status_code, update_resp.text[:200])
        return False

    submit_indexnow([post["link"]])
    submit_bing([post["link"]])
    log.info("refresh.ok post_id=%d query=%r new_title=%r",
             post_id, query, new_title)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh low-CTR posts.")
    ap.add_argument("--limit", type=int, default=5,
                    help="Max posts to refresh per run.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print proposed changes, do not update WP.")
    args = ap.parse_args()

    wp = WordPressClient()
    n_done = 0

    if gsc_available():
        log.info("refresh.mode=gsc")
        for opp in top_refresh_candidates(n=args.limit):
            if _refresh_one_gsc(opp, wp, args.dry_run):
                n_done += 1
    else:
        log.info("refresh.mode=wp_fallback reason=gsc_unavailable")
        candidates = _wp_fallback_candidates(limit=args.limit)
        for post in candidates:
            # Without GSC, we don't know the target query — use the
            # category name as a coarse proxy.
            cats = post.get("categories", [])
            query = post["title"]["rendered"]  # self-paraphrase
            if _refresh_post(post, query, position=20.0, ctr=0.01,
                             wp=wp, dry_run=args.dry_run):
                n_done += 1

    log.info("refresh.done n=%d limit=%d", n_done, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
