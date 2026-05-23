"""Google Analytics helpers via Composio OAuth."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .composio_client import ComposioClient, available as composio_available
from .config import settings
from .logging_utils import log


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
    return bool(
        composio_available()
        and settings.composio.google_analytics_account_id
        and settings.composio.ga4_property
    )


def is_available() -> bool:
    return _ga_ready()


def list_account_summaries() -> list[dict[str, Any]]:
    if not _ga_ready():
        log.info("ga.skip reason=not_configured")
        return []
    result = ComposioClient().execute(
        "GOOGLE_ANALYTICS_LIST_ACCOUNT_SUMMARIES",
        connected_account_id=settings.composio.google_analytics_account_id,
    )
    if not result.successful:
        log.warning("ga.account_summaries err=%s", result.error)
        return []
    return result.data.get("accountSummaries", []) if isinstance(result.data, dict) else []


def run_report(*, dimensions: list[str], metrics: list[str], days: int = 28, limit: int = 100,
               order_metric: str | None = None, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    if not _ga_ready():
        log.info("ga.skip reason=not_configured")
        return {}
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    args: dict[str, Any] = {
        "property": settings.composio.ga4_property,
        "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "limit": limit,
    }
    if order_metric:
        args["orderBys"] = [{"desc": True, "metric": {"metricName": order_metric}}]
    if filters:
        args["dimensionFilter"] = filters
    result = ComposioClient().execute(
        "GOOGLE_ANALYTICS_RUN_REPORT",
        connected_account_id=settings.composio.google_analytics_account_id,
        arguments=args,
    )
    if not result.successful:
        log.warning("ga.run_report err=%s", result.error)
        return {}
    return result.data if isinstance(result.data, dict) else {}


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
