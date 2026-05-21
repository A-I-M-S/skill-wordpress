"""Clean up artifacts/ — deletes large media files, preserves state JSON.

What this DOES delete:
  - artifacts/shorts/**/*.mp4          (Seedance + muxed shorts videos)
  - artifacts/shorts/**/*.mp3          (edge-tts narration)
  - artifacts/shorts/**/*.wav          (any intermediate audio)
  - artifacts/seedream/**/*.{png,jpg,jpeg,webp}
  - artifacts/seedance/**/*.mp4
  - Empty subdirectories left behind

What this NEVER deletes:
  - *_state.json  (publish_state, shorts_state, promote_state, etc.)
  - *.json        anywhere in artifacts/
  - logs/         (never touched)

Default retention: keep files newer than 24 hours. Use --hours to
override, --all to nuke everything (state files still safe), or
--dry-run to preview.

Recommended cron — once a day at 03:00 Singapore time:
  0 19 * * * cd /path/to/skill-wordpress && /usr/bin/python3 scripts/cleanup.py >> logs/wp.log 2>&1

(19 UTC = 03 SGT)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
ARTIFACTS = PROJECT_ROOT / "artifacts"

PURGEABLE_EXTS = {".mp4", ".mp3", ".wav", ".m4a", ".png", ".jpg", ".jpeg", ".webp"}


def find_targets(root: Path, older_than_seconds: float) -> list[Path]:
    if not root.exists():
        return []
    now = time.time()
    targets = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() == ".json":
            continue  # preserve all state files
        if p.suffix.lower() not in PURGEABLE_EXTS:
            continue
        age = now - p.stat().st_mtime
        if age >= older_than_seconds:
            targets.append(p)
    return targets


def prune_empty_dirs(root: Path) -> int:
    """Remove empty subdirectories under root (but keep root itself)."""
    if not root.exists():
        return 0
    removed = 0
    for d in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and d != root and not any(d.iterdir()):
            d.rmdir()
            removed += 1
    return removed


def human_size(bytes_: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f}{unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f}TB"


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up artifacts/.")
    parser.add_argument("--hours", type=float, default=24,
                        help="Delete files older than this many hours (default 24).")
    parser.add_argument("--all", action="store_true",
                        help="Delete everything purgeable regardless of age.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted without deleting.")
    args = parser.parse_args()

    threshold = 0 if args.all else args.hours * 3600
    targets = find_targets(ARTIFACTS, threshold)

    total_bytes = sum(p.stat().st_size for p in targets)
    print(f"cleanup: {len(targets)} files, {human_size(total_bytes)} "
          f"({'ALL ages' if args.all else f'older than {args.hours}h'})")

    if args.dry_run:
        for p in targets[:25]:
            print(f"  would delete: {p.relative_to(PROJECT_ROOT)}")
        if len(targets) > 25:
            print(f"  ... and {len(targets) - 25} more")
        return 0

    deleted = 0
    for p in targets:
        try:
            p.unlink()
            deleted += 1
        except Exception as exc:
            print(f"  ! failed: {p}: {exc}", file=sys.stderr)

    empty_dirs = prune_empty_dirs(ARTIFACTS)
    print(f"cleanup: deleted={deleted} freed={human_size(total_bytes)} "
          f"empty_dirs_removed={empty_dirs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
