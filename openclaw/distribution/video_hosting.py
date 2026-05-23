"""Make a local mp4 publicly fetchable so Reels/LinkedIn APIs can pull it.

Meta (IG/FB Reels) and LinkedIn need a publicly accessible video_url —
they fetch it themselves rather than accepting multipart uploads. We
solve that by uploading the mp4 to WordPress as a media attachment and
returning the WP CDN URL.

This costs us nothing (WP already hosts our images) and uses the same
auth we already have. The video file is auto-purged with the rest of
artifacts/ by scripts/cleanup.py — but the WP copy persists, which is
fine because Meta/LinkedIn finish the fetch within seconds.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..logging_utils import log
from ..wordpress.client import WordPressClient

_cache: dict[str, str] = {}


def host_video(video_path: Path) -> Optional[str]:
    """Upload mp4 to WP media; return the public URL. Idempotent per path."""
    key = str(video_path)
    if key in _cache:
        return _cache[key]
    try:
        wp = WordPressClient()
        media = wp.upload_media(video_path)
        url = media.get("source_url") or media.get("guid", {}).get("rendered")
        if not url:
            log.warning("video_hosting.upload no_url media=%s", media)
            return None
        _cache[key] = url
        log.info("video_hosting.uploaded url=%s size=%dKB", url, video_path.stat().st_size // 1024)
        return url
    except Exception as exc:
        log.warning("video_hosting.upload err=%s", exc)
        return None
