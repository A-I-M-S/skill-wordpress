"""Sync SEO growth signals into Google Sheets.

Usage:
    python -m scripts.growth_dashboard
    python -m scripts.growth_dashboard --days 28 --gsc-limit 200

If GROWTH_SHEET_ID is not set, the script creates a new Google Sheet and logs
its id. Add that id to .env as GROWTH_SHEET_ID for future runs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw import analytics
from openclaw.growth_sheet import ensure_growth_sheet, sync_analytics, sync_opportunities
from openclaw.gsc import fetch_opportunities, list_sites
from openclaw.logging_utils import log


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync InsightGinie SEO growth dashboard.")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--gsc-limit", type=int, default=500)
    args = ap.parse_args()

    sheet_id = ensure_growth_sheet()
    if sheet_id:
        print(f"GROWTH_SHEET_ID={sheet_id}")

    sites = list_sites()
    for site in sites:
        log.info("gsc.site url=%s permission=%s", site.get("siteUrl"), site.get("permissionLevel"))

    opps = fetch_opportunities(lookback_days=args.days, row_limit=args.gsc_limit)
    opps.sort(key=lambda o: -o.score)
    sync_opportunities(opps[:200], spreadsheet_id=sheet_id)

    if analytics.is_available():
        pages = analytics.top_pages(days=args.days, limit=100)
        refs = analytics.referrals(days=args.days, limit=100)
        sync_analytics(pages, refs, spreadsheet_id=sheet_id)

    log.info("growth_dashboard.done opps=%d", len(opps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
