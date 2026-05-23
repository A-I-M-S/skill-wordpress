"""Google Search Console integration — find your highest-leverage pages.

Preferred mode uses Composio OAuth, so there is no Google service-account JSON
in this repo. Legacy service-account mode remains as a fallback.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

from .config import PROJECT_ROOT, settings
from .composio_client import ComposioClient, available as composio_available
from .logging_utils import log


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


def _gsc_service_account_path() -> Optional[str]:
    path = os.getenv("GSC_SERVICE_ACCOUNT_FILE", "gsc-service-account.json")
    if not os.path.isabs(path):
        path = str(PROJECT_ROOT / path)
    return path if os.path.exists(path) else None


def _gsc_service():
    """Build an authenticated Search Console API service. Returns None
    if creds are missing (caller falls back to WP-only mode)."""
    creds_path = _gsc_service_account_path()
    if not creds_path:
        log.info("gsc.skip reason=no_service_account_file")
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        log.warning("gsc.skip reason=google_api_libs_missing")
        return None
    creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
    )
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
    if composio_available() and settings.composio.gsc_account_id:
        result = ComposioClient().execute(
            "GOOGLE_SEARCH_CONSOLE_LIST_SITES",
            connected_account_id=settings.composio.gsc_account_id,
        )
        if result.successful:
            return result.data.get("siteEntry", []) if isinstance(result.data, dict) else []
        log.warning("gsc.composio_list_sites err=%s", result.error)
    return []


def fetch_opportunities(
    *,
    site_url: Optional[str] = None,
    lookback_days: int = 28,
    row_limit: int = 200,
) -> List[Opportunity]:
    site_url = site_url or settings.composio.gsc_site_url or os.getenv("GSC_SITE_URL")
    if not site_url:
        log.info("gsc.skip reason=no_site_url")
        return []

    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=lookback_days)

    if composio_available() and settings.composio.gsc_account_id:
        result = ComposioClient().execute(
            "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY",
            connected_account_id=settings.composio.gsc_account_id,
            arguments={
                "site_url": site_url,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "dimensions": ["page", "query"],
                "row_limit": row_limit,
                "data_state": "all",
            },
        )
        if result.successful and isinstance(result.data, dict):
            opps = _rows_to_opportunities(result.data.get("rows", []))
            log.info("gsc.composio_fetched n=%d range=%s..%s", len(opps), start, end)
            return opps
        log.warning("gsc.composio_query_err err=%s", result.error)

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
    by_page: dict[str, Opportunity] = {}
    # Dedup by page — keep the best-scoring query per page
    for o in opps:
        if o.score <= 0 or o.page.rstrip("/") == (settings.composio.gsc_site_url or "").rstrip("/"):
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
    if composio_available() and settings.composio.gsc_account_id and settings.composio.gsc_site_url:
        return True
    return bool(os.getenv("GSC_SITE_URL")) and _gsc_service_account_path() is not None
