"""Google Search Console integration — find your highest-leverage pages.

Uses a Google service-account JSON (see openclaw/google_auth.py). Skips
gracefully when the credential file is absent.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

from .config import settings
from .google_auth import credentials, service_account_path
from .logging_utils import log

_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


@dataclass
class Opportunity:
    page: str
    query: str
    impressions: int
    clicks: int
    ctr: float
    position: float

    @property
    def score(self) -> float:
        """Higher = better refresh candidate.

        - Lots of impressions = there's existing demand.
        - Low CTR for the position = title/snippet is letting us down.
        - Position 6-15 = page is RIGHT on the edge of page 1, biggest
          single improvement per unit of work.
        """
        if self.impressions < 10:
            return 0.0
        position_bonus = max(0.0, 15.0 - abs(self.position - 10))  # peak at pos 10
        ctr_gap = max(0.0, 0.05 - self.ctr)  # how far below 5% CTR
        return self.impressions * (1 + ctr_gap * 20) * (1 + position_bonus / 10)


def _site_url() -> str:
    return os.getenv("GSC_SITE_URL") or settings.composio.gsc_site_url


def _gsc_service():
    """Build an authenticated Search Console API service. Returns None
    if creds are missing (caller falls back to WP-only mode)."""
    creds = credentials(_SCOPES)
    if not creds:
        log.info("gsc.skip reason=no_service_account_file")
        return None
    try:
        from googleapiclient.discovery import build
    except ImportError:
        log.warning("gsc.skip reason=google_api_libs_missing")
        return None
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def _rows_to_opportunities(rows: list[dict]) -> list[Opportunity]:
    opps: list[Opportunity] = []
    for row in rows:
        keys = row.get("keys", [])
        if len(keys) < 2:
            continue
        page, query = keys[0], keys[1]
        opps.append(Opportunity(
            page=page,
            query=query,
            impressions=int(row.get("impressions", 0)),
            clicks=int(row.get("clicks", 0)),
            ctr=float(row.get("ctr", 0.0)),
            position=float(row.get("position", 100.0)),
        ))
    return opps


def list_sites() -> list[dict]:
    svc = _gsc_service()
    if not svc:
        return []
    try:
        resp = svc.sites().list().execute()
    except Exception as exc:
        log.warning("gsc.list_sites_err err=%s", exc)
        return []
    return resp.get("siteEntry", []) if isinstance(resp, dict) else []


def fetch_opportunities(
    *,
    site_url: Optional[str] = None,
    lookback_days: int = 28,
    row_limit: int = 200,
) -> List[Opportunity]:
    site_url = site_url or _site_url()
    if not site_url:
        log.info("gsc.skip reason=no_site_url")
        return []

    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=lookback_days)

    svc = _gsc_service()
    if not svc:
        return []

    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["page", "query"],
        "rowLimit": row_limit,
        "dataState": "all",
    }

    try:
        resp = svc.searchanalytics().query(siteUrl=site_url, body=body).execute()
    except Exception as exc:
        log.warning("gsc.query_err err=%s", exc)
        return []

    opps = _rows_to_opportunities(resp.get("rows", []))
    log.info("gsc.fetched n=%d range=%s..%s", len(opps), start, end)
    return opps


def top_refresh_candidates(n: int = 5) -> List[Opportunity]:
    """Return the N highest-leverage pages to refresh."""
    opps = fetch_opportunities()
    opps.sort(key=lambda o: -o.score)
    site = (_site_url() or "").rstrip("/")
    by_page: dict[str, Opportunity] = {}
    # Dedup by page — keep the best-scoring query per page
    for o in opps:
        if o.score <= 0 or o.page.rstrip("/") == site:
            continue
        if o.page not in by_page:
            by_page[o.page] = o
    top = list(by_page.values())[:n]
    for t in top:
        log.info(
            "gsc.candidate score=%.0f page=%s q=%r imp=%d pos=%.1f ctr=%.2f%%",
            t.score, t.page, t.query, t.impressions, t.position, t.ctr * 100,
        )
    return top


def is_available() -> bool:
    return bool(_site_url() and service_account_path())
