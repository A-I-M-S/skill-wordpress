"""YouTube Shorts auto-publishing with ByteDance Seedance + edge-tts.

Pipeline per Short:
  1. LLM-generate a single-beat ~10-15s spoken script from the article.
  2. Seedance text-to-video: native 9:16, 1080p, 10-15s.
     (Optionally i2v from the existing Seedream hero image.)
  3. edge-tts produces neural TTS narration (free, no API key).
  4. ffmpeg muxes video + audio, trims to whichever is shorter,
     adds caption overlay with the article title (optional).
  5. YouTube Data API v3 uploads the mp4 with title/description/tags.

YouTube OAuth (one-time):
  - Create OAuth desktop client in Google Cloud Console.
  - Save the JSON as `youtube-client-secrets.json` (path configurable).
  - First run opens a browser to authorize; token is cached to
    `youtube-token.json`.

Cadence note:
  YouTube throttles new/AI-only Shorts channels. The sweet spot for
  AI-generated Shorts is 1/day at a consistent time, NOT 6/day. The
  orchestrator schedules this once daily — do not raise it before you
  have 50+ Shorts and a healthy retention curve.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from ..config import ARTIFACTS_DIR, settings
from ..logging_utils import log
from ..video.seedance import SeedanceClient, build_shorts_prompt
from ..video_safety import build_safe_prompt, is_safe_hero_url
from .base import PostPayload


def post(
    payload: PostPayload,
    *,
    hero_image_url: Optional[str] = None,
    narration_voice: str = "en-US-AriaNeural",
) -> Optional[str]:
    """Generate and upload a YouTube Short. Returns the YouTube video URL,
    or None on any failure (never raises — keeps the pipeline alive)."""
    if not settings.distribution.youtube_shorts:
        log.info("shorts.skip reason=flag_off")
        return None
    if not settings.seedance.api_key:
        log.info("shorts.skip reason=no_seedance_key")
        return None
    try:
        out_dir = ARTIFACTS_DIR / "shorts" / re.sub(r"\W+", "-", payload.title.lower())[:60]
        out_dir.mkdir(parents=True, exist_ok=True)

        script = _build_short_script(payload)
        log.info("shorts.script len=%d", len(script))

        wants_native_audio = settings.seedance.generate_audio
        video_path, used_native_audio = _generate_video_with_audio_fallback(
            payload, hero_image_url, out_dir, prefer_native_audio=wants_native_audio,
        )
        log.info("shorts.video generated path=%s native_audio=%s",
                 video_path, used_native_audio)

        if used_native_audio:
            final = video_path
            log.info("shorts.audio source=seedance_native (skipping edge-tts)")
        else:
            audio = _generate_narration(script, out_dir, narration_voice)
            final = _mux(video_path, audio, out_dir)
            log.info("shorts.composed path=%s", final)

        youtube_url = _upload_to_youtube(final, payload, script)
        fan_out_video_distribution(payload, final)
        return youtube_url
    except Exception as exc:
        log.warning("shorts.fail err=%s", exc)
        return None


def _generate_video_with_audio_fallback(
    payload: PostPayload,
    hero_image_url: Optional[str],
    out_dir: Path,
    *,
    prefer_native_audio: bool,
) -> tuple[Path, bool]:
    """Try native audio first. On ByteDance's OutputAudioSensitiveContentDetected
    (or any 'audio' + 'sensitive' moderation hit), retry once with audio
    disabled. Returns (video_path, used_native_audio)."""
    try:
        path = _generate_video(payload, hero_image_url, out_dir,
                               generate_audio=prefer_native_audio if prefer_native_audio else False)
        return path, prefer_native_audio
    except RuntimeError as exc:
        err = str(exc).lower()
        is_audio_moderation = (
            "outputaudiosensitivecontentdetected" in err
            or ("audio" in err and "sensitive" in err)
        )
        if not (prefer_native_audio and is_audio_moderation):
            raise
        log.warning("shorts.audio_moderation_retry reason=%s", exc)
        path = _generate_video(payload, hero_image_url, out_dir, generate_audio=False)
        return path, False


# ---- script generation ----------------------------------------------------

def _build_short_script(payload: PostPayload) -> str:
    """A tight ~28-35 word narration that fits 10-15s at ~150wpm."""
    from ..llm import LLMClient

    llm = LLMClient()
    prompt = (
        "Write a 28-35 word YouTube Shorts narration for the article below. "
        "Punchy, conversational, end with 'Link in bio for the full breakdown.' "
        "No emojis, no hashtags, no quotes. Plain text only.\n\n"
        f"TITLE: {payload.title}\n"
        f"EXCERPT: {payload.excerpt}"
    )
    text = llm.complete_text(prompt, max_tokens=120) or payload.excerpt
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---- Seedance video -------------------------------------------------------

def _generate_video(
    payload: PostPayload,
    hero_image_url: Optional[str],
    out_dir: Path,
    script: Optional[str] = None,
    *,
    generate_audio: Optional[bool] = None,
) -> Path:
    client = SeedanceClient()
    prompt = build_safe_prompt(payload.title, payload.excerpt[:200])
    log.info("shorts.safe_prompt %r", prompt[:140])
    if hero_image_url and is_safe_hero_url(hero_image_url):
        log.info("shorts.seedance mode=i2v audio=%s hero=%s",
                 generate_audio, hero_image_url)
        video = client.image_to_video(
            prompt, hero_image_url, out_dir=out_dir, generate_audio=generate_audio,
        )
    else:
        log.info("shorts.seedance mode=t2v audio=%s hero_unsafe=%s",
                 generate_audio, hero_image_url)
        video = client.text_to_video(
            prompt, out_dir=out_dir, generate_audio=generate_audio,
        )
    return video.path


# ---- TTS narration --------------------------------------------------------

def _generate_narration(text: str, out_dir: Path, voice: str) -> Path:
    import edge_tts  # lazy import — only needed when shorts run

    path = out_dir / "narration.mp3"

    async def _run() -> None:
        communicator = edge_tts.Communicate(text, voice)
        await communicator.save(str(path))

    asyncio.run(_run())
    return path


# ---- ffmpeg mux -----------------------------------------------------------

def _mux(video: Path, audio: Path, out_dir: Path) -> Path:
    out = out_dir / "final.mp4"
    # -shortest: trim to the shorter of audio/video so we never have silence
    # -map 0:v -map 1:a: take video from input0, audio from input1 (replace original)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out),
    ]
    log.debug("shorts.ffmpeg cmd=%s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-400:]}")
    return out


# ---- YouTube upload -------------------------------------------------------

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _youtube_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token_path = Path(settings.youtube.token_file)
    creds: Optional[Credentials] = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "YouTube token missing or invalid; run `python3 scripts/youtube_auth.py --manual`, "
                "approve the URL, then run `python3 scripts/youtube_auth.py --redirect-url '<final localhost URL>'`."
            )
        token_path.write_text(creds.to_json())
        token_path.chmod(0o600)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _upload_to_youtube(mp4: Path, payload: PostPayload, script: str) -> Optional[str]:
    if not settings.youtube.enabled:
        log.info("shorts.skip_upload reason=youtube_disabled path=%s", mp4)
        return None
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        log.warning("shorts.skip_upload reason=google-api-python-client_missing")
        return None

    yt = _youtube_service()
    title = payload.title[:95]  # 100 char hard limit; leave room for #Shorts
    description = (
        f"{script}\n\n"
        f"Full breakdown: {payload.url}\n\n"
        f"#Shorts #{' #'.join(t.replace(' ', '') for t in payload.tags[:5])}"
    )
    body = {
        "snippet": {
            "title": f"{title} #Shorts",
            "description": description,
            "tags": payload.tags[:10],
            "categoryId": settings.youtube.category_id,
        },
        "status": {
            "privacyStatus": settings.youtube.privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(mp4), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("shorts.upload progress=%d%%", int(status.progress() * 100))
    video_id = response.get("id")
    if not video_id:
        log.warning("shorts.upload no_id resp=%s", response)
        return None
    url = f"https://www.youtube.com/shorts/{video_id}"
    log.info("shorts.uploaded url=%s", url)
    return url


# ---- fan-out to other video platforms ------------------------------------

def fan_out_video_distribution(payload: PostPayload, mp4_path: Path) -> None:
    """Post the same mp4 to every enabled video platform. Each in its own
    try/except so a single failure never blocks the others."""
    flags = settings.distribution
    targets = []
    if flags.instagram_reels:
        from . import instagram_reels
        targets.append(("instagram_reels", instagram_reels.post_video))
    if flags.facebook_reels:
        from . import facebook_reels
        targets.append(("facebook_reels", facebook_reels.post_video))
    if flags.linkedin_video:
        from . import linkedin_video
        targets.append(("linkedin_video", linkedin_video.post_video))
    if flags.threads_video:
        from . import threads_video
        targets.append(("threads_video", threads_video.post_video))
    if flags.tiktok_draft:
        from . import tiktok_draft
        targets.append(("tiktok_draft", tiktok_draft.post_video))

    if not targets:
        log.info("shorts.fanout skip reason=no_video_platforms_enabled")
        return

    log.info("shorts.fanout starting platforms=%d", len(targets))
    for name, fn in targets:
        try:
            fn(payload, mp4_path)
        except Exception as exc:
            log.warning("shorts.fanout %s err=%s", name, exc)
