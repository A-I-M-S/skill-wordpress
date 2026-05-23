"""Google Sheets growth dashboard via Composio."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence

from .composio_client import ComposioClient, available as composio_available
from .config import settings
from .logging_utils import log


def is_available() -> bool:
    return bool(composio_available() and settings.composio.google_sheets_account_id)


def _execute(tool: str, args: dict) -> dict:
    result = ComposioClient().execute(
        tool,
        connected_account_id=settings.composio.google_sheets_account_id,
        arguments=args,
    )
    if not result.successful:
        raise RuntimeError(f"{tool} failed: {result.error}")
    return result.data if isinstance(result.data, dict) else {}


def ensure_growth_sheet() -> str | None:
    if not is_available():
        log.info("growth_sheet.skip reason=not_configured")
        return settings.composio.growth_sheet_id
    if settings.composio.growth_sheet_id:
        return settings.composio.growth_sheet_id
    data = _execute("GOOGLESHEETS_CREATE_GOOGLE_SHEET1", {"title": "InsightGinie SEO Growth Dashboard"})
    spreadsheet_id = (
        data.get("spreadsheetId")
        or data.get("spreadsheet_id")
        or data.get("id")
        or data.get("spreadsheet", {}).get("spreadsheetId")
    )
    if spreadsheet_id:
        log.info("growth_sheet.created spreadsheet_id=%s", spreadsheet_id)
    else:
        log.warning("growth_sheet.created_but_no_id data=%s", data)
    return spreadsheet_id


def _add_sheet_if_missing(spreadsheet_id: str, sheet_name: str) -> None:
    try:
        _execute("GOOGLESHEETS_ADD_SHEET", {
            "spreadsheet_id": spreadsheet_id,
            "title": sheet_name,
        })
        log.info("growth_sheet.add_sheet ok sheet=%s", sheet_name)
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" not in msg and "duplicate" not in msg:
            log.warning("growth_sheet.add_sheet err sheet=%s err=%s", sheet_name, exc)


def write_rows(sheet_name: str, rows: Sequence[Sequence[object]], *, spreadsheet_id: str | None = None,
               first_cell: str = "A1") -> None:
    if not rows:
        return
    spreadsheet_id = spreadsheet_id or ensure_growth_sheet()
    if not spreadsheet_id:
        return
    args = {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "first_cell_location": first_cell,
        "value_input_option": "USER_ENTERED",
        "values": [list(r) for r in rows],
    }
    try:
        _execute("GOOGLESHEETS_BATCH_UPDATE", args)
        log.info("growth_sheet.write ok sheet=%s rows=%d", sheet_name, len(rows))
    except Exception as exc:
        if "not found" in str(exc).lower():
            _add_sheet_if_missing(spreadsheet_id, sheet_name)
            try:
                _execute("GOOGLESHEETS_BATCH_UPDATE", args)
                log.info("growth_sheet.write ok sheet=%s rows=%d", sheet_name, len(rows))
                return
            except Exception as retry_exc:
                exc = retry_exc
        log.warning("growth_sheet.write err sheet=%s err=%s", sheet_name, exc)


def sync_opportunities(opportunities: Iterable, *, spreadsheet_id: str | None = None) -> str | None:
    sid = spreadsheet_id or ensure_growth_sheet()
    if not sid:
        return None
    now = datetime.now(timezone.utc).isoformat()
    rows = [["synced_at", "score", "page", "query", "impressions", "clicks", "ctr", "position"]]
    for o in opportunities:
        rows.append([now, round(o.score, 2), o.page, o.query, o.impressions, o.clicks, round(o.ctr, 4), round(o.position, 2)])
    write_rows("GSC Opportunities", rows, spreadsheet_id=sid)
    return sid


def sync_analytics(page_metrics: Iterable, referral_metrics: Iterable, *, spreadsheet_id: str | None = None) -> str | None:
    sid = spreadsheet_id or ensure_growth_sheet()
    if not sid:
        return None
    now = datetime.now(timezone.utc).isoformat()
    page_rows = [["synced_at", "path", "sessions", "active_users", "views", "engagement_rate"]]
    for p in page_metrics:
        page_rows.append([now, p.path, p.sessions, p.active_users, p.views, round(p.engagement_rate, 4)])
    ref_rows = [["synced_at", "source", "medium", "sessions", "active_users"]]
    for r in referral_metrics:
        ref_rows.append([now, r.source, r.medium, r.sessions, r.active_users])
    write_rows("GA Pages", page_rows, spreadsheet_id=sid)
    write_rows("GA Referrals", ref_rows, spreadsheet_id=sid)
    return sid


def append_promotion_log(rows: Sequence[Sequence[object]], *, spreadsheet_id: str | None = None) -> str | None:
    sid = spreadsheet_id or ensure_growth_sheet()
    if not sid:
        return None
    header = [["logged_at", "channel", "status", "url", "detail"]]
    write_rows("Promotion Log", header + [list(r) for r in rows], spreadsheet_id=sid)
    return sid
