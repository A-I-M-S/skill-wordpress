"""Google Sheets growth dashboard via a Google service account (Sheets API v4)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence

from .config import settings
from .google_auth import credentials, service_account_path
from .logging_utils import log

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _service():
    creds = credentials(_SCOPES)
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build
    except ImportError:
        log.warning("growth_sheet.skip reason=google_api_libs_missing")
        return None
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def is_available() -> bool:
    return bool(service_account_path() and settings.composio.growth_sheet_id)


def ensure_growth_sheet() -> str | None:
    if settings.composio.growth_sheet_id:
        return settings.composio.growth_sheet_id
    svc = _service()
    if not svc:
        log.info("growth_sheet.skip reason=not_configured")
        return None
    try:
        data = svc.spreadsheets().create(
            body={"properties": {"title": "InsightGinie SEO Growth Dashboard"}}
        ).execute()
    except Exception as exc:
        log.warning("growth_sheet.create_err err=%s", exc)
        return None
    spreadsheet_id = data.get("spreadsheetId")
    if spreadsheet_id:
        log.info("growth_sheet.created spreadsheet_id=%s", spreadsheet_id)
    else:
        log.warning("growth_sheet.created_but_no_id data=%s", data)
    return spreadsheet_id


def _existing_sheets(svc, spreadsheet_id: str) -> set[str]:
    meta = svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties.title"
    ).execute()
    return {s["properties"]["title"] for s in meta.get("sheets", [])}


def _add_sheet_if_missing(svc, spreadsheet_id: str, sheet_name: str) -> None:
    try:
        if sheet_name in _existing_sheets(svc, spreadsheet_id):
            return
        svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
        ).execute()
        log.info("growth_sheet.add_sheet ok sheet=%s", sheet_name)
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" not in msg and "duplicate" not in msg:
            log.warning("growth_sheet.add_sheet err sheet=%s err=%s", sheet_name, exc)


def write_rows(sheet_name: str, rows: Sequence[Sequence[object]], *, spreadsheet_id: str | None = None,
               first_cell: str = "A1") -> None:
    if not rows:
        return
    svc = _service()
    if not svc:
        log.info("growth_sheet.skip reason=not_configured")
        return
    spreadsheet_id = spreadsheet_id or ensure_growth_sheet()
    if not spreadsheet_id:
        return
    _add_sheet_if_missing(svc, spreadsheet_id, sheet_name)
    rng = f"'{sheet_name}'!{first_cell}"
    values = [list(r) for r in rows]
    try:
        svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=rng,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()
        log.info("growth_sheet.write ok sheet=%s rows=%d", sheet_name, len(rows))
    except Exception as exc:
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
