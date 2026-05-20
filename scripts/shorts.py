"""Generate and publish one YouTube Short for an existing WP post.

Strategy:
- Default behaviour picks a recent post that does not yet have a Short
  recorded in artifacts/shorts_state.json. This avoids duplicate Shorts.
- Use --url to force a specific post.
- Use --dry-run to compose the mp4 locally without uploading to YouTube.

Recommended cadence: 1× per day at a consistent time slot (e.g. 20:00 SGT).
Do NOT run more than once per 6 hours — YouTube throttles new channels
that upload AI-generated Shorts at high volume.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw.config import ARTIFACTS_DIR, settings  # noqa: E402
from openclaw.distribution import youtube_shorts  # noqa: E402
from openclaw.distribution.base import PostPayload  # noqa: E402
from openclaw.logging_utils import log  # noqa: E402


STATE_FILE = ARTIFACTS_DIR / "shorts_state.json"
MIN_INTERVAL_HOURS = 6  # hard floor between Shorts uploads


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"shorts": []}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"shorts": []}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _hours_since_last(state: dict) -> float:
    if not state.get("shorts"):
        return 1e9
    last = state["shorts"][-1]["created_at"]
    dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def _already_published_urls(state: dict) -> set[str]:
    return {entry["wp_url"] for entry in state.get("shorts", [])}


def _pick_post(state: dict, n_recent: int = 50) -> Optional[dict]:
    cfg = settings.wp
    resp = requests.get(
        f"{cfg.api_base}/posts",
        params={"per_page": n_recent, "_fields": "id,link,title,excerpt,tags"},
        timeout=30,
    )
    resp.raise_for_status()
    posts = resp.json()
    already = _already_published_urls(state)
    candidates = [p for p in posts if p["link"] not in already]
    if not candidates:
        log.info("shorts.no_candidates — all recent posts already have a Short")
        return None
    return random.choice(candidates)


def _to_payload(wp_post: dict) -> PostPayload:
    return PostPayload(
        title=wp_post["title"]["rendered"],
        excerpt=_strip_html(wp_post["excerpt"]["rendered"]),
        url=wp_post["link"],
        html_content="",
        md_content="",
        tags=[],
    )


def _strip_html(text: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one YouTube Short with Seedance.")
    parser.add_argument("--url", help="Specific WP post URL")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compose the mp4 locally; do not upload")
    parser.add_argument("--force", action="store_true",
                        help="Skip the 6h cooldown")
    args = parser.parse_args()

    state = _load_state()
    elapsed = _hours_since_last(state)
    if not args.force and elapsed < MIN_INTERVAL_HOURS:
        log.info("shorts.cooldown elapsed=%.1fh required=%dh", elapsed, MIN_INTERVAL_HOURS)
        return 0

    if args.url:
        resp = requests.get(args.url, headers={"Accept": "application/json"}, timeout=30)
        wp_post = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None
        if not wp_post:
            # Fall back to slug lookup
            slug = args.url.rstrip("/").rsplit("/", 1)[-1]
            r2 = requests.get(f"{settings.wp.api_base}/posts", params={"slug": slug}, timeout=30)
            r2.raise_for_status()
            arr = r2.json()
            if not arr:
                log.error("shorts.url_not_found %s", args.url)
                return 1
            wp_post = arr[0]
    else:
        wp_post = _pick_post(state)
        if not wp_post:
            return 0

    payload = _to_payload(wp_post)
    log.info("shorts.target title=%r url=%s", payload.title, payload.url)

    if args.dry_run:
        # Re-enable the flag locally for the dry-run so we exercise the pipeline
        # without actually uploading.
        import os
        os.environ["DIST_YOUTUBE_SHORTS"] = "true"
        os.environ["YOUTUBE_ENABLED"] = "false"
        # Reload settings module
        from importlib import reload
        from openclaw import config as _config
        reload(_config)

    url = youtube_shorts.post(payload)
    state.setdefault("shorts", []).append({
        "wp_url": payload.url,
        "wp_title": payload.title,
        "youtube_url": url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
    })
    _save_state(state)
    print(url or "(dry-run, see artifacts/shorts/...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
