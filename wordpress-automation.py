"""Backward-compatible shim for the legacy entry point.

The real logic now lives in `scripts/publish.py`. This file exists so the
existing cron jobs (`python3 wordpress-automation.py`) keep working
without modification while you migrate.

Recommended cron (max 4 posts/day — the new pipeline enforces this anyway):
    0 */6 * * * cd /path/to/skill-wordpress && python3 wordpress-automation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.publish import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
