"""Google Analytics (GA4) helpers via a Google service account (Data API v1beta)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import requests

from .config import settings
from .google_auth import bearer_token, service_account_path
from .logging_utils import log

_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
_DATA_URL = "https://analyticsdata.googleapis.com/v1beta"
_ADMIN_URL = "https://analyticsadmin.googleapis.com/v1beta"


@dataclass
class PageMetric:
    path: str
    sessions: int
    active_users: int
    views: int
    engagement_rate: float


@dataclass
class ReferralMetric:
    source: str
    medium: str
    sessions: int
    active_users: int


def _ga_ready() -> bool:
    return bool(service_account_path() and settings.composio.ga4_property)


def is_available() -> bool:
    return _ga_ready()


def list_account_summaries() -> list[dict[str, Any]]:
    if not _ga_ready():
        log.info("ga.skip reason=not_configured")
        return []
    token = bearer_token(_SCOPES)
    if not token:
        return []
    try:
        r = requests.get(
            f"{_ADMIN_URL}/accountSummaries",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if r.status_code >= 400:
            log.warning("ga.account_summaries err=status_%s body=%s", r.status_code, r.text[:300])
            return []
        return r.json().get("accountSummaries", [])
    except Exception as exc:
        log.warning("ga.account_summaries err=%s", exc)
        return []


def run_report(*, dimensions: list[str], metrics: list[str], days: int = 28, limit: int = 100,
               order_metric: str | None = None, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    if not _ga_ready():
        log.info("ga.skip reason=not_configured")
        return {}
    token = bearer_token(_SCOPES)
    if not token:
        return {}
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    body: dict[str, Any] = {
        "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "limit": limit,
    }
    if order_metric:
        body["orderBys"] = [{"desc": True, "metric": {"metricName": order_metric}}]
    if filters:
        body["dimensionFilter"] = filters
    prop = settings.composio.ga4_property
    try:
        r = requests.post(
            f"{_DATA_URL}/{prop}:runReport",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            data=json.dumps(body),
            timeout=30,
        )
        if r.status_code >= 400:
            log.warning("ga.run_report err=status_%s body=%s", r.status_code, r.text[:300])
            return {}
        return r.json() if isinstance(r.json(), dict) else {}
    except Exception as exc:
        log.warning("ga.run_report err=%s", exc)
        return {}


def _metric_value(row: dict[str, Any], idx: int, default: float = 0) -> float:
    try:
        return float(row.get("metricValues", [])[idx].get("value", default))
    except Exception:
        return default


def top_pages(days: int = 28, limit: int = 50) -> list[PageMetric]:
    data = run_report(
        dimensions=["pagePath"],
        metrics=["sessions", "activeUsers", "screenPageViews", "engagementRate"],
        days=days,
        limit=limit,
        order_metric="sessions",
    )
    out: list[PageMetric] = []
    for row in data.get("rows", []):
        dims = row.get("dimensionValues", [])
        path = dims[0].get("value", "") if dims else ""
        out.append(PageMetric(
            path=path,
            sessions=int(_metric_value(row, 0)),
            active_users=int(_metric_value(row, 1)),
            views=int(_metric_value(row, 2)),
            engagement_rate=_metric_value(row, 3),
        ))
    return out


def referrals(days: int = 28, limit: int = 50) -> list[ReferralMetric]:
    data = run_report(
        dimensions=["sessionSource", "sessionMedium"],
        metrics=["sessions", "activeUsers"],
        days=days,
        limit=limit,
        order_metric="sessions",
    )
    out: list[ReferralMetric] = []
    for row in data.get("rows", []):
        dims = row.get("dimensionValues", [])
        out.append(ReferralMetric(
            source=dims[0].get("value", "") if len(dims) > 0 else "",
            medium=dims[1].get("value", "") if len(dims) > 1 else "",
            sessions=int(_metric_value(row, 0)),
            active_users=int(_metric_value(row, 1)),
        ))
    return out
