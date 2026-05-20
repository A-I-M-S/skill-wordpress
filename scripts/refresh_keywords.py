"""Refresh the keyword pool from DDG / YouTube autosuggest.

Run this once after install, then weekly via cron to keep the pool fresh:
    0 4 * * 1 cd /path/to/skill-wordpress && python3 scripts/refresh_keywords.py

Idempotent — safe to run any time. Categories with >=30 keywords already
pooled are skipped unless --force is passed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw.config import settings  # noqa: E402
from openclaw.keywords import refresh_pool, load_pool  # noqa: E402
from openclaw.logging_utils import log  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh keyword pool.")
    ap.add_argument("--force", action="store_true", help="Rebuild every category.")
    ap.add_argument("--category", type=str, default=None,
                    help="Only refresh this category name.")
    args = ap.parse_args()

    cats = json.loads(settings.publishing.category_file.read_text())
    if args.category:
        cats = [c for c in cats if c["name"] == args.category]
        if not cats:
            print(f"No such category: {args.category}", file=sys.stderr)
            return 2

    log.info("kw.refresh start n_categories=%d force=%s", len(cats), args.force)
    pool = refresh_pool(cats, force=args.force)

    sizes = sorted(((name, len(kws)) for name, kws in pool.items()),
                   key=lambda x: -x[1])
    print(f"{'category':<28} {'keywords':>8}")
    print("-" * 38)
    for name, count in sizes:
        print(f"{name:<28} {count:>8}")
    print(f"{'TOTAL':<28} {sum(c for _, c in sizes):>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
