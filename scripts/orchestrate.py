"""One-shot orchestrator: figures out what to do this hour, then does it.

Recommended cron — ONE line replaces every other entry:

    0 * * * * cd /path/to/skill-wordpress && /usr/bin/python3 scripts/orchestrate.py

Schedule (Singapore time by default; set ORCHESTRATOR_TZ to override):

  Hour (SGT)  Action(s)
  ----------  ------------------------------------------------------
  04          refresh keyword pool (Mondays only) + publish
  10, 16, 22  publish.py
  20          shorts.py + promote.py
  even hrs    promote.py  (re-share existing posts, highest ROI)
  odd hrs     idle

Daily totals: 4 publish + 1 short + ~6 promote = ~11 runs/day.
Weekly: +1 keyword-pool refresh on Monday 04:00.

Pass --what to see what THIS hour would do without running anything.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openclaw.logging_utils import log  # noqa: E402

TZ = ZoneInfo(os.getenv("ORCHESTRATOR_TZ", "Asia/Singapore"))

PUBLISH_HOURS = {4, 10, 16, 22}
SHORTS_HOUR = 20
WEEKLY_REFRESH_HOUR = 4
WEEKLY_REFRESH_WEEKDAY = 0  # 0 = Monday


def _plan(now: datetime) -> list[tuple[str, list[str]]]:
    """Return the list of (label, [script, *args]) jobs for this hour."""
    hour = now.hour
    jobs: list[tuple[str, list[str]]] = []

    if hour == WEEKLY_REFRESH_HOUR and now.weekday() == WEEKLY_REFRESH_WEEKDAY:
        jobs.append(("refresh_keywords", ["refresh_keywords.py"]))

    if hour in PUBLISH_HOURS:
        jobs.append(("publish", ["publish.py"]))
    elif hour == SHORTS_HOUR:
        jobs.append(("shorts", ["shorts.py"]))
        jobs.append(("promote", ["promote.py"]))
    elif hour % 2 == 0:
        jobs.append(("promote", ["promote.py"]))

    return jobs


def _run(label: str, script_args: list[str]) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / script_args[0]), *script_args[1:]]
    log.info("orchestrate.run %s -> %s", label, " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT)
    log.info("orchestrate.done %s rc=%d", label, proc.returncode)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="OpenClaw hourly orchestrator.")
    ap.add_argument("--what", action="store_true",
                    help="Print the planned jobs for THIS hour and exit.")
    args = ap.parse_args()

    now = datetime.now(TZ)
    jobs = _plan(now)
    log.info(
        "orchestrate.tick local_time=%s hour=%d weekday=%d jobs=%d",
        now.isoformat(timespec="minutes"), now.hour, now.weekday(), len(jobs),
    )

    if args.what:
        if not jobs:
            print(f"{now.isoformat(timespec='minutes')} — idle")
        else:
            for label, script_args in jobs:
                print(f"{now.isoformat(timespec='minutes')} — {label}: {' '.join(script_args)}")
        return 0

    if not jobs:
        log.info("orchestrate.idle hour=%d — nothing scheduled", now.hour)
        return 0

    rc = 0
    for label, script_args in jobs:
        rc |= _run(label, script_args)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
