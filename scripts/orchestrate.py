"""One-shot orchestrator: figures out what to do this hour, then does it.

This is the recommended cron entry — run every hour, and the script
decides whether to publish, promote, or generate a Short based on the
schedule below.

    0 * * * * cd /path/to/skill-wordpress && python3 scripts/orchestrate.py

Schedule (Singapore time by default; set ORCHESTRATOR_TZ to override):
  - publish.py : at 04:00, 10:00, 16:00, 22:00  (every 6h, 4/day)
  - promote.py : at every even hour NOT covered by publish
  - shorts.py  : at 20:00  (1×/day, peak SGT engagement)

Why this shape:
  - 4 posts/day is the hard cap on new content.
  - Promotion of existing 8k posts is the real traffic lever; runs ~10×/day.
  - YouTube Shorts are 1×/day to stay clear of the algorithm's spam filter.
"""
from __future__ import annotations

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


def _run(label: str, script: str, *args: str) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *args]
    log.info("orchestrate.run %s -> %s", label, " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT)
    log.info("orchestrate.done %s rc=%d", label, proc.returncode)
    return proc.returncode


def main() -> int:
    now = datetime.now(TZ)
    hour = now.hour
    log.info("orchestrate.tick local_time=%s hour=%d", now.isoformat(timespec="minutes"), hour)

    rc = 0
    if hour in PUBLISH_HOURS:
        rc |= _run("publish", "publish.py")
    elif hour == SHORTS_HOUR:
        # Run promote AND shorts at the peak hour.
        rc |= _run("shorts", "shorts.py")
        rc |= _run("promote", "promote.py")
    elif hour % 2 == 0:
        rc |= _run("promote", "promote.py")
    else:
        log.info("orchestrate.idle hour=%d — nothing scheduled", hour)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
