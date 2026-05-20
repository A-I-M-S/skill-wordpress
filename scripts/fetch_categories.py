"""Fetch all WP categories and write them to data/categories.full.json.

Edit `data/curated_categories.json` by hand to your chosen niche subset.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw.config import DATA_DIR, settings  # noqa: E402
from openclaw.logging_utils import log  # noqa: E402


def fetch_all() -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        url = f"{settings.wp.api_base}/categories"
        resp = requests.get(url, params={"per_page": 100, "page": page}, timeout=30)
        if not resp.ok:
            log.warning("fetch_categories.page%d status=%d", page, resp.status_code)
            break
        data = resp.json()
        if not data:
            break
        out.extend({"id": c["id"], "name": c["name"], "count": c.get("count", 0)} for c in data)
        page += 1
    return out


def main() -> int:
    cats = fetch_all()
    DATA_DIR.mkdir(exist_ok=True)
    target = DATA_DIR / "categories.full.json"
    target.write_text(json.dumps(cats, indent=2))
    log.info("fetch_categories.done count=%d path=%s", len(cats), target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
