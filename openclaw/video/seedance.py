"""ByteDance Seedance video generation (BytePlus Ark / Volcano Engine).

Seedance is async: submit a task, poll until succeeded, download the mp4.

Docs:
- BytePlus international: https://docs.byteplus.com/en/docs/ModelArk/VideoGeneration
- Volcano Engine CN:     https://www.volcengine.com/docs/82379/1520757

Endpoints / models default to BytePlus international, override via env:
  SEEDANCE_ENDPOINT   - tasks endpoint, default
                        https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks
  SEEDANCE_MODEL      - default `seedance-1-0-pro-250528` (use lite for cheaper)
  SEEDANCE_RESOLUTION - 480p | 720p | 1080p   (default 1080p)
  SEEDANCE_DURATION   - seconds, 5..15        (default 10)
  SEEDANCE_RATIO      - 9:16 (Shorts) | 16:9 | 1:1  (default 9:16)

The prompt is built with Seedance's inline-flag syntax
(`--ratio 9:16 --duration 10 --resolution 1080p --camera_fixed false`)
so a single string carries both subject and render directives.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from ..config import ARTIFACTS_DIR, settings
from ..logging_utils import log


DEFAULT_ENDPOINT = "https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks"


@dataclass
class SeedanceVideo:
    path: Path          # local mp4 path
    duration_s: int
    resolution: str
    prompt: str
    task_id: str


class SeedanceClient:
    """Minimal async-task client for Seedance video generation."""

    def __init__(self) -> None:
        cfg = settings.seedance
        if not cfg.api_key:
            raise RuntimeError("SEEDANCE_API_KEY not set")
        self.api_key = cfg.api_key
        self.endpoint = cfg.endpoint or DEFAULT_ENDPOINT
        self.model = cfg.model
        self.resolution = cfg.resolution
        self.duration = max(5, min(int(cfg.duration), 15))
        self.ratio = cfg.ratio
        self.poll_interval = 5
        self.poll_timeout = 600  # 10 min hard cap

    # ---- public ----
    def text_to_video(
        self,
        prompt: str,
        *,
        out_dir: Optional[Path] = None,
        camera_fixed: bool = False,
    ) -> SeedanceVideo:
        """Generate a video from a text prompt and return the local mp4 path."""
        full_prompt = self._build_prompt(prompt, camera_fixed=camera_fixed)
        task_id = self._submit({
            "model": self.model,
            "content": [{"type": "text", "text": full_prompt}],
        })
        video_url = self._poll(task_id)
        return self._download(task_id, video_url, full_prompt, out_dir)

    def image_to_video(
        self,
        prompt: str,
        image_url: str,
        *,
        out_dir: Optional[Path] = None,
        camera_fixed: bool = False,
    ) -> SeedanceVideo:
        """Animate an existing image (e.g. a Seedream hero) into a video."""
        full_prompt = self._build_prompt(prompt, camera_fixed=camera_fixed)
        task_id = self._submit({
            "model": self.model,
            "content": [
                {"type": "text", "text": full_prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        })
        video_url = self._poll(task_id)
        return self._download(task_id, video_url, full_prompt, out_dir)

    # ---- internals ----
    def _build_prompt(self, prompt: str, *, camera_fixed: bool) -> str:
        # Seedance reads inline `--flag value` directives from the prompt string.
        flags = [
            f"--ratio {self.ratio}",
            f"--duration {self.duration}",
            f"--resolution {self.resolution}",
            f"--camera_fixed {'true' if camera_fixed else 'false'}",
        ]
        return f"{prompt.strip()} " + " ".join(flags)

    def _submit(self, payload: dict) -> str:
        log.info("seedance.submit model=%s duration=%ss ratio=%s",
                 self.model, self.duration, self.ratio)
        resp = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"seedance submit failed {resp.status_code}: {resp.text[:300]}")
        task_id = resp.json().get("id") or resp.json().get("task_id")
        if not task_id:
            raise RuntimeError(f"seedance submit returned no task id: {resp.text[:300]}")
        log.info("seedance.task_submitted id=%s", task_id)
        return task_id

    def _poll(self, task_id: str) -> str:
        url = f"{self.endpoint.rstrip('/')}/{task_id}"
        deadline = time.time() + self.poll_timeout
        while time.time() < deadline:
            time.sleep(self.poll_interval)
            try:
                resp = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=30,
                )
                resp.raise_for_status()
            except Exception as exc:
                log.warning("seedance.poll_err id=%s err=%s", task_id, exc)
                continue

            data = resp.json()
            status = data.get("status", "").lower()
            if status == "succeeded":
                # Response shape: content.video_url OR content[0].video_url
                content = data.get("content") or {}
                if isinstance(content, list):
                    content = content[0] if content else {}
                video_url = content.get("video_url") or data.get("video_url")
                if not video_url:
                    raise RuntimeError(f"seedance succeeded but no video_url: {data}")
                log.info("seedance.task_succeeded id=%s", task_id)
                return video_url
            if status in {"failed", "cancelled"}:
                raise RuntimeError(f"seedance task {task_id} {status}: {data}")
            log.debug("seedance.poll id=%s status=%s", task_id, status)

        raise RuntimeError(f"seedance task {task_id} did not complete in {self.poll_timeout}s")

    def _download(
        self,
        task_id: str,
        video_url: str,
        prompt: str,
        out_dir: Optional[Path],
    ) -> SeedanceVideo:
        out_dir = out_dir or (ARTIFACTS_DIR / "seedance")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{task_id}.mp4"
        with requests.get(video_url, stream=True, timeout=180) as r:
            r.raise_for_status()
            with path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
        log.info("seedance.downloaded path=%s size=%dKB",
                 path, path.stat().st_size // 1024)
        return SeedanceVideo(
            path=path,
            duration_s=self.duration,
            resolution=self.resolution,
            prompt=prompt,
            task_id=task_id,
        )


def build_shorts_prompt(article_title: str, beat: str) -> str:
    """Compose a Seedance prompt for a single ~10s YouTube Short beat."""
    return (
        f"Cinematic vertical short-form video. Topic: {article_title}. "
        f"Scene: {beat}. "
        "High contrast, modern editorial style, subtle motion, "
        "centered subject with negative space for caption overlay, "
        "no text in frame, no logos, no watermarks."
    )
