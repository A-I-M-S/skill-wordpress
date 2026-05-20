"""ByteDance Seedream image generation (BytePlus Ark / Volcano Engine).

Docs:
- BytePlus international: https://docs.byteplus.com/en/docs/ModelArk/ImageGeneration
- Volcano Engine CN:     https://www.volcengine.com/docs/82379/1541523

Endpoint and model name are configurable via env (SEEDREAM_ENDPOINT,
SEEDREAM_MODEL). Returns the generated image as bytes plus the prompt
echo for logging / attribution.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from ..config import ARTIFACTS_DIR, settings
from ..logging_utils import log


@dataclass
class SeedreamImage:
    bytes_: bytes
    prompt: str
    saved_to: Optional[Path] = None
    remote_url: Optional[str] = None


class SeedreamClient:
    def __init__(self) -> None:
        cfg = settings.seedream
        self.api_key = cfg.api_key
        self.endpoint = cfg.endpoint
        self.model = cfg.model
        self.size = cfg.size

    def _post(self, payload: dict) -> dict:
        if not self.api_key:
            raise RuntimeError("SEEDREAM_API_KEY not set")
        response = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
        return response.json()

    def generate(
        self,
        prompt: str,
        size: Optional[str] = None,
        save_dir: Optional[Path] = None,
        seed: Optional[int] = None,
    ) -> SeedreamImage:
        body = {
            "model": self.model,
            "prompt": prompt,
            "size": size or self.size,
            "response_format": "url",
        }
        if seed is not None:
            body["seed"] = seed

        log.info("seedream.generate model=%s size=%s prompt=%r", self.model, body["size"], prompt[:80])
        data = self._post(body)

        item = (data.get("data") or [{}])[0]
        remote_url: Optional[str] = item.get("url")
        b64: Optional[str] = item.get("b64_json")

        if b64:
            img_bytes = base64.b64decode(b64)
        elif remote_url:
            img_bytes = requests.get(remote_url, timeout=60).content
        else:
            raise RuntimeError(f"Seedream returned no image payload: {data}")

        saved_to: Optional[Path] = None
        target_dir = save_dir or ARTIFACTS_DIR / "seedream"
        target_dir.mkdir(parents=True, exist_ok=True)
        saved_to = target_dir / f"seedream-{int(time.time())}.png"
        saved_to.write_bytes(img_bytes)

        return SeedreamImage(bytes_=img_bytes, prompt=prompt, saved_to=saved_to, remote_url=remote_url)


def build_blog_hero_prompt(title: str, tags: list[str]) -> str:
    """Compose a prompt suited for a 1:1 / 16:9 blog hero image."""
    tag_hint = ", ".join(tags[:3]) if tags else "technology, AI"
    return (
        f"Editorial blog hero illustration for the article '{title}'. "
        f"Subject: {tag_hint}. Style: clean, modern, slightly minimal, "
        f"dark background with subtle accent lighting, professional tech "
        f"magazine aesthetic, no text, no watermarks, no logos, photorealistic."
    )


def build_short_vertical_prompt(scene: str) -> str:
    """Vertical 9:16 image prompt for YouTube Shorts frames."""
    return (
        f"Cinematic vertical illustration, 9:16 aspect ratio. Scene: {scene}. "
        f"Highly detailed, dramatic lighting, modern tech editorial style, "
        f"no text overlays, no captions, no watermarks."
    )
