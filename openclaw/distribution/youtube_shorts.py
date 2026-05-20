"""YouTube Shorts auto-publishing.

Pipeline per post:
  1. LLM-generate a 30-45s spoken script from the article (3 beats).
  2. Seedream generates one vertical 9:16 image per beat (3 images).
  3. edge-tts produces neural TTS narration (free, no API key).
  4. ffmpeg composes images (Ken Burns) + narration → mp4 (1080x1920, 30fps).
  5. YouTube Data API v3 uploads the mp4 with title/description/tags.

Auth (one-time):
  - Create OAuth desktop client in Google Cloud Console, download JSON
    to skill-wordpress/youtube-client-secrets.json (path is configurable
    via YOUTUBE_CLIENT_SECRETS).
  - First run will open a browser to authorize; token is cached to
    youtube-token.json.

Dependencies:
  pip install google-api-python-client google-auth-oauthlib edge-tts
  (ffmpeg must be on PATH)
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from pathlib import Path
from typing import List, Optional

import requests

from ..config import ARTIFACTS_DIR, settings
from ..images.seedream import SeedreamClient, build_short_vertical_prompt
from ..logging_utils import log
from .base import PostPayload

SHORTS_DIR = ARTIFACTS_DIR / "shorts"
SHORTS_DIR.mkdir(parents=True, exist_ok=True)


def _script_from_article(payload: PostPayload) -> List[str]:
    """Use OpenRouter to compress article → 3 short scene-beats (~12s each)."""
    api_key = settings.llm.openrouter_key
    if not api_key:
        # Fallback: split excerpt into 3 sentences
        sentences = re.split(r"(?<=[.!?])\s+", payload.excerpt)
        return (sentences + [payload.title, payload.title])[:3]

    prompt = (
        "Compress this blog post into EXACTLY 3 spoken beats for a 35-second "
        "vertical short. Each beat: 2-3 sentences, hook → insight → CTA. "
        "Return JSON: {\"beats\": [\"...\", \"...\", \"...\"]} only.\n\n"
        f"Title: {payload.title}\nExcerpt: {payload.excerpt}\n"
        f"Body (truncated): {payload.md_content[:2500]}"
    )
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": settings.llm.primary_model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "max_tokens": 600,
            },
            timeout=120,
        )
        raw = resp.json()["choices"][0]["message"]["content"]
        beats = json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group(0))["beats"]
        return [str(b).strip() for b in beats][:3]
    except Exception as exc:
        log.warning("yt.script_llm err=%s falling back to excerpt", exc)
        return [payload.excerpt, payload.title, "Read the full breakdown at InsightGinie."]


async def _tts(text: str, out_path: Path, voice: str = "en-US-AndrewNeural") -> None:
    import edge_tts  # local import — only required when this distributor runs
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))


def _render_video(images: List[Path], audios: List[Path], out_path: Path) -> None:
    """Compose vertical 1080x1920 mp4 with one image per audio clip + Ken Burns zoom."""
    if len(images) != len(audios):
        raise ValueError("images and audios must match in length")

    work = out_path.parent / f"work-{int(time.time())}"
    work.mkdir(exist_ok=True)
    segments: List[Path] = []

    for idx, (img, aud) in enumerate(zip(images, audios)):
        # Find audio duration
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(aud),
            ],
            capture_output=True, text=True, check=True,
        )
        duration = max(2.0, float(probe.stdout.strip()))
        seg = work / f"seg{idx}.mp4"
        # Slow zoom-in on a 1080x1920 canvas, image fitted with blurred background.
        vf = (
            f"scale=1080:-1,"
            f"crop=1080:1920:0:'(ih-1920)/2',"
            f"zoompan=z='min(zoom+0.0015,1.15)':d={int(duration*30)}:s=1080x1920:fps=30"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-loop", "1", "-i", str(img),
                "-i", str(aud),
                "-vf", vf,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(seg),
            ],
            check=True,
        )
        segments.append(seg)

    concat_list = work / "concat.txt"
    concat_list.write_text("\n".join(f"file '{s.resolve()}'" for s in segments))
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", str(out_path),
        ],
        check=True,
    )
    log.info("yt.render ok path=%s", out_path)


def _upload(video_path: Path, payload: PostPayload, title_override: Optional[str] = None) -> Optional[str]:
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.auth.transport.requests import Request as GReq
    except ImportError:
        log.warning("yt.upload skip reason=google_libs_missing")
        return None

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    token_path = Path(settings.youtube.token_file)
    secrets_path = Path(settings.youtube.client_secrets_file)
    creds: Optional[Credentials] = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GReq())
        else:
            if not secrets_path.exists():
                log.warning("yt.upload skip reason=client_secrets_missing path=%s", secrets_path)
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), scopes)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    youtube = build("youtube", "v3", credentials=creds)
    short_title = (title_override or f"{payload.title} #shorts")[:95]
    body = {
        "snippet": {
            "title": short_title,
            "description": f"{payload.excerpt}\n\nFull article: {payload.url}\n\n#Shorts " + " ".join(f"#{t.replace(' ', '')}" for t in payload.tags[:5]),
            "tags": payload.tags[:15],
            "categoryId": settings.youtube.category_id,
        },
        "status": {"privacyStatus": settings.youtube.privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    video_id = response.get("id")
    if video_id:
        url = f"https://youtu.be/{video_id}"
        log.info("yt.upload ok url=%s", url)
        return url
    return None


def post(payload: PostPayload) -> Optional[str]:
    """Full pipeline: returns the published YouTube URL or None."""
    if not settings.youtube.enabled:
        log.info("yt.skip reason=disabled (set YOUTUBE_ENABLED=true)")
        return None
    if not settings.seedream.api_key:
        log.info("yt.skip reason=no_seedream_key")
        return None

    try:
        beats = _script_from_article(payload)
        log.info("yt.beats count=%d", len(beats))

        seedream = SeedreamClient()
        images: List[Path] = []
        for i, beat in enumerate(beats):
            scene = f"{payload.title}. Visualization beat {i+1}: {beat[:200]}"
            img = seedream.generate(build_short_vertical_prompt(scene), size="1024x1792")
            assert img.saved_to is not None
            images.append(img.saved_to)

        audios: List[Path] = []
        tts_dir = SHORTS_DIR / f"tts-{int(time.time())}"
        tts_dir.mkdir(parents=True, exist_ok=True)
        for i, beat in enumerate(beats):
            out = tts_dir / f"beat{i}.mp3"
            asyncio.run(_tts(beat, out))
            audios.append(out)

        video_path = SHORTS_DIR / f"short-{int(time.time())}.mp4"
        _render_video(images, audios, video_path)

        return _upload(video_path, payload)
    except Exception as exc:
        log.warning("yt.pipeline err=%s", exc)
        return None
