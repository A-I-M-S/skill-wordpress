"""Thin wrapper around the WordPress REST API."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

from ..config import settings
from ..logging_utils import log


class WordPressClient:
    def __init__(self) -> None:
        cfg = settings.wp
        if not (cfg.host and cfg.user and cfg.password):
            raise RuntimeError("WP_HOST / WP_USER / WP_PW must be set")
        self.base = cfg.api_base
        self.auth = HTTPBasicAuth(cfg.user, cfg.password)
        self.host = cfg.host

    # ---- tags ----
    def ensure_tag(self, name: str) -> int:
        existing = requests.get(
            f"{self.base}/tags",
            params={"search": name, "per_page": 5},
            auth=self.auth,
            timeout=30,
        ).json()
        for tag in existing:
            if tag.get("name", "").lower() == name.lower():
                return tag["id"]
        created = requests.post(
            f"{self.base}/tags",
            auth=self.auth,
            headers={"Content-Type": "application/json"},
            json={"name": name},
            timeout=30,
        ).json()
        return created["id"]

    def ensure_tags(self, names: List[str]) -> List[int]:
        return [self.ensure_tag(n) for n in names if n.strip()]

    # ---- media ----
    def get_media(self, media_id: int) -> Dict[str, Any]:
        response = requests.get(f"{self.base}/media/{media_id}", auth=self.auth, timeout=30)
        response.raise_for_status()
        return response.json()

    def upload_media(self, path: Path, alt_text: str = "", title: str = "") -> Dict[str, Any]:
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        with path.open("rb") as fh:
            response = requests.post(
                f"{self.base}/media",
                auth=self.auth,
                headers={
                    "Content-Disposition": f'attachment; filename="{path.name}"',
                    "Content-Type": mime,
                },
                data=fh.read(),
                timeout=120,
            )
        response.raise_for_status()
        media = response.json()
        if alt_text or title:
            requests.post(
                f"{self.base}/media/{media['id']}",
                auth=self.auth,
                json={"alt_text": alt_text, "title": title},
                timeout=30,
            )
        return media

    # ---- posts ----
    def create_post(
        self,
        title: str,
        content: str,
        excerpt: str,
        category_ids: List[int],
        tag_ids: List[int],
        featured_media_id: Optional[int],
        status: str = "publish",
    ) -> Dict[str, Any]:
        payload = {
            "title": title,
            "content": content,
            "excerpt": excerpt,
            "status": status,
            "categories": category_ids,
            "tags": tag_ids,
        }
        if featured_media_id:
            payload["featured_media"] = featured_media_id

        response = requests.post(
            f"{self.base}/posts",
            auth=self.auth,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        post = response.json()
        log.info("wp.create_post id=%s url=%s", post.get("id"), post.get("link"))
        return post

    def list_recent_posts(self, category_id: int, per_page: int = 5) -> List[Dict[str, Any]]:
        response = requests.get(
            f"{self.base}/posts",
            params={"categories": category_id, "per_page": per_page, "orderby": "date", "order": "desc"},
            auth=self.auth,
            timeout=30,
        )
        return response.json() if response.ok else []

    def random_post(self) -> Optional[Dict[str, Any]]:
        """Fetch a recent post for promote.py (cheap proxy for 'random')."""
        response = requests.get(
            f"{self.base}/posts",
            params={"per_page": 50, "orderby": "date", "order": "desc", "_embed": 1},
            auth=self.auth,
            timeout=30,
        )
        if not response.ok:
            return None
        posts = response.json()
        import random as _r
        return _r.choice(posts) if posts else None
