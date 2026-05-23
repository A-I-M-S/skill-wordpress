"""Central configuration. All env vars are accessed here — nowhere else."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

PKG_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PKG_ROOT.parent
DATA_DIR = PROJECT_ROOT / "data"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)


def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    val = os.getenv(key, default)
    return val if val not in (None, "") else default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = (os.getenv(key) or "").lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _env_list(key: str, default: List[str]) -> List[str]:
    raw = os.getenv(key)
    if not raw:
        return default
    return [p.strip() for p in raw.split(",") if p.strip()]


def _resolve_project_path(value: str) -> str:
    """Return an absolute path: if `value` is absolute use it, else resolve
    relative to PROJECT_ROOT so things work no matter what cwd the script
    was launched from."""
    p = Path(value)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return str(p)


@dataclass(frozen=True)
class WordPressConfig:
    host: str = field(default_factory=lambda: _env("WP_HOST", "") or "")
    user: str = field(default_factory=lambda: _env("WP_USER", "") or "")
    password: str = field(default_factory=lambda: _env("WP_PW", "") or "")
    media_range_start: int = field(default_factory=lambda: _env_int("MEDIA_RANGE_START", 1000))
    media_range_end: int = field(default_factory=lambda: _env_int("MEDIA_RANGE_END", 2000))

    @property
    def api_base(self) -> str:
        return f"https://{self.host}/wp-json/wp/v2"


@dataclass(frozen=True)
class LLMConfig:
    openrouter_key: Optional[str] = field(default_factory=lambda: _env("OR_SK"))
    primary_model: str = field(
        default_factory=lambda: _env("LLM_PRIMARY_MODEL", "google/gemini-3.1-flash-lite")
    )
    fallback_models: List[str] = field(
        default_factory=lambda: _env_list(
            "LLM_FALLBACK_MODELS",
            ["anthropic/claude-3.5-haiku", "openai/gpt-4o-mini"],
        )
    )
    max_tokens: int = field(default_factory=lambda: _env_int("LLM_MAX_TOKENS", 4000))
    min_words: int = field(default_factory=lambda: _env_int("MIN_WORDS", 1200))


@dataclass(frozen=True)
class SeedreamConfig:
    """ByteDance Seedream (Volcano Engine / BytePlus Ark) image generation."""

    api_key: Optional[str] = field(default_factory=lambda: _env("SEEDREAM_API_KEY"))
    # Default: BytePlus international endpoint. Set SEEDREAM_ENDPOINT to override
    # for Volcano Engine China (https://ark.cn-beijing.volces.com/api/v3/images/generations).
    endpoint: str = field(
        default_factory=lambda: _env(
            "SEEDREAM_ENDPOINT",
            "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations",
        ) or "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations"
    )
    model: str = field(default_factory=lambda: _env("SEEDREAM_MODEL", "seedream-5-0-260128") or "seedream-5-0-260128")
    size: str = field(default_factory=lambda: _env("SEEDREAM_SIZE", "2K"))
    watermark: bool = field(default_factory=lambda: _env_bool("SEEDREAM_WATERMARK", True))


@dataclass(frozen=True)
class SeedanceConfig:
    """ByteDance Seedance (Volcano Engine / BytePlus Ark) video generation.

    Async task model — submit, poll, download. Native 9:16 for Shorts.
    Duration is clamped to 5..15s by the client."""

    api_key: Optional[str] = field(default_factory=lambda: _env("SEEDANCE_API_KEY"))
    endpoint: str = field(
        default_factory=lambda: _env(
            "SEEDANCE_ENDPOINT",
            "https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks",
        )
    )
    model: str = field(
        default_factory=lambda: _env("SEEDANCE_MODEL", "dreamina-seedance-2-0-fast-260128")
    )
    resolution: str = field(default_factory=lambda: _env("SEEDANCE_RESOLUTION", "1080p"))
    duration: int = field(default_factory=lambda: _env_int("SEEDANCE_DURATION", 10))
    ratio: str = field(default_factory=lambda: _env("SEEDANCE_RATIO", "9:16"))
    generate_audio: bool = field(default_factory=lambda: _env_bool("SEEDANCE_GENERATE_AUDIO", True))
    watermark: bool = field(default_factory=lambda: _env_bool("SEEDANCE_WATERMARK", False))


@dataclass(frozen=True)
class RedditConfig:
    client_id: Optional[str] = field(default_factory=lambda: _env("REDDIT_CLIENT_ID"))
    client_secret: Optional[str] = field(default_factory=lambda: _env("REDDIT_CLIENT_SECRET"))
    username: Optional[str] = field(default_factory=lambda: _env("REDDIT_USERNAME"))
    password: Optional[str] = field(default_factory=lambda: _env("REDDIT_PASSWORD"))
    user_agent: str = field(
        default_factory=lambda: _env("REDDIT_USER_AGENT", "openclaw-bot:v0.2 (by /u/aloycwl)")
    )
    # Allowlist: only post to subs you actually moderate or that explicitly permit self-promo.
    # Posting to broad subs without prior karma will shadowban. Start small.
    allowed_subs: List[str] = field(
        default_factory=lambda: _env_list("REDDIT_ALLOWED_SUBS", ["u_aloycwl"])
    )
    min_minutes_between_posts: int = field(
        default_factory=lambda: _env_int("REDDIT_MIN_INTERVAL_MIN", 240)
    )


@dataclass(frozen=True)
class HackerNewsConfig:
    """HN has no official posting API. We semi-automate: build a one-click
    submission URL and deliver it via Telegram for human approval. This
    preserves account quality and avoids HN's strict anti-bot heuristics."""

    enabled: bool = field(default_factory=lambda: _env_bool("HN_ENABLED", True))
    notify_chat_id: Optional[str] = field(
        default_factory=lambda: _env("HN_NOTIFY_TELEGRAM_CHAT_ID")
    )


@dataclass(frozen=True)
class YouTubeConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("YOUTUBE_ENABLED", False))
    client_secrets_file: str = field(
        default_factory=lambda: _resolve_project_path(
            _env("YOUTUBE_CLIENT_SECRETS", "youtube-client-secrets.json")
            or "youtube-client-secrets.json"
        )
    )
    token_file: str = field(
        default_factory=lambda: _resolve_project_path(
            _env("YOUTUBE_TOKEN_FILE", "youtube-token.json")
            or "youtube-token.json"
        )
    )
    privacy: str = field(default_factory=lambda: _env("YOUTUBE_PRIVACY", "public") or "public")
    category_id: str = field(default_factory=lambda: _env("YOUTUBE_CATEGORY_ID", "28") or "28")


@dataclass(frozen=True)
class DistributionFlags:
    linkedin: bool = field(default_factory=lambda: _env_bool("DIST_LINKEDIN", True))
    bluesky: bool = field(default_factory=lambda: _env_bool("DIST_BLUESKY", True))
    threads: bool = field(default_factory=lambda: _env_bool("DIST_THREADS", True))
    facebook: bool = field(default_factory=lambda: _env_bool("DIST_FACEBOOK", True))
    telegram: bool = field(default_factory=lambda: _env_bool("DIST_TELEGRAM", True))
    discord: bool = field(default_factory=lambda: _env_bool("DIST_DISCORD", True))
    nostr: bool = field(default_factory=lambda: _env_bool("DIST_NOSTR", True))
    # Hashnode default-off: their spam filter is aggressive against
    # auto-cross-posted AI content and ban appeals rarely succeed.
    hashnode: bool = field(default_factory=lambda: _env_bool("DIST_HASHNODE", False))
    reddit: bool = field(default_factory=lambda: _env_bool("DIST_REDDIT", False))
    hackernews: bool = field(default_factory=lambda: _env_bool("DIST_HACKERNEWS", True))
    youtube_shorts: bool = field(default_factory=lambda: _env_bool("DIST_YOUTUBE_SHORTS", False))
    instagram_reels: bool = field(default_factory=lambda: _env_bool("DIST_INSTAGRAM_REELS", False))
    facebook_reels: bool = field(default_factory=lambda: _env_bool("DIST_FACEBOOK_REELS", False))
    linkedin_video: bool = field(default_factory=lambda: _env_bool("DIST_LINKEDIN_VIDEO", False))
    threads_video: bool = field(default_factory=lambda: _env_bool("DIST_THREADS_VIDEO", False))
    tiktok_draft: bool = field(default_factory=lambda: _env_bool("DIST_TIKTOK_DRAFT", False))
    # OFF by default — duplicate content footgun.
    wordpress_com_mirror: bool = field(default_factory=lambda: _env_bool("DIST_WP_COM", False))
    # OFF by default — high ban risk.
    devto: bool = field(default_factory=lambda: _env_bool("DIST_DEVTO", False))


@dataclass(frozen=True)
class PublishingConfig:
    # Hard daily cap. After Google's 2024 spam policy, anything above ~4/day
    # on a single domain is a scaled-content-abuse signal. Do NOT raise this
    # until the site is out of Helpful Content review and topical authority
    # is established. Even 4 is aggressive for a generalist site.
    max_posts_per_day: int = field(default_factory=lambda: _env_int("MAX_POSTS_PER_DAY", 4))
    min_minutes_between_posts: int = field(
        default_factory=lambda: _env_int("MIN_MINUTES_BETWEEN_POSTS", 240)
    )
    state_file: Path = field(default_factory=lambda: ARTIFACTS_DIR / "publish_state.json")
    title_similarity_threshold: float = field(
        default_factory=lambda: float(_env("TITLE_SIM_THRESHOLD", "0.80") or "0.80")
    )
    # Curated niche file — leaner than the original 60-cat dump.
    category_file: Path = field(
        default_factory=lambda: DATA_DIR
        / (_env("CATEGORY_FILE", "curated_categories.json") or "curated_categories.json")
    )
    author_name: str = field(default_factory=lambda: _env("AUTHOR_NAME", "Aloy CWL") or "Aloy CWL")
    author_url: str = field(
        default_factory=lambda: _env("AUTHOR_URL", "https://insightginie.com/about")
        or "https://insightginie.com/about"
    )


@dataclass(frozen=True)
class Settings:
    wp: WordPressConfig = field(default_factory=WordPressConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    seedream: SeedreamConfig = field(default_factory=SeedreamConfig)
    seedance: SeedanceConfig = field(default_factory=SeedanceConfig)
    reddit: RedditConfig = field(default_factory=RedditConfig)
    hn: HackerNewsConfig = field(default_factory=HackerNewsConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    distribution: DistributionFlags = field(default_factory=DistributionFlags)
    publishing: PublishingConfig = field(default_factory=PublishingConfig)
    indexnow_key: Optional[str] = field(default_factory=lambda: _env("INDEXNOW_KEY"))
    bing_api_key: Optional[str] = field(default_factory=lambda: _env("BING_WMT_API_KEY"))


# Module-level singleton — import this everywhere else.
settings = Settings()
