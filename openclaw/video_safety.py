"""Pre-flight safety for Seedance video generation.

Today's `OutputVideoSensitiveContentDetected.PolicyViolation` was
"copyright restrictions" — Seedance refused to animate a WP media
attachment that contained a real person / brand likeness. The fix has
two layers:

  1. NEVER feed an arbitrary WP media-roulette image as i2v input. The
     hero MUST come from Seedream, which we generated ourselves with
     known-safe abstract prompts.

  2. The animation PROMPT itself must be abstract — no people, no
     branded objects, no real places. We rewrite the article title /
     excerpt into a generic conceptual scene description before
     handing it to Seedance.

This module is the single chokepoint for both checks.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from .topic_filter import is_safe_topic
from .logging_utils import log


# Phrases / patterns to STRIP from a prompt because they are likely to
# trigger Seedance's content moderator.
_STRIP_PATTERNS = [
    re.compile(r"\b(CEO|CFO|COO|CTO|president|founder|director|chairman|chairwoman)\b", re.I),
    re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof|Rev|Sir|Dame|Lord|Senator|Congressman|Governor|Mayor)\.?\s+[A-Z][a-z]+", re.I),
    # Branded suffixes — keep the core idea, drop the brand.
    re.compile(r"\b[A-Z][\w&-]*\s+(Inc|Corp|Corporation|Ltd|Limited|LLC|PLC|Bank|Holdings|Group)\b"),
    # URLs / handles
    re.compile(r"https?://\S+"),
    re.compile(r"@\w+"),
    # Currency / specific quarters
    re.compile(r"\$\d[\d,.]*[MBK]?"),
    re.compile(r"\bQ[1-4]\s+\d{4}\b"),
]


# Generic abstract scene library — when a topic is too risky to animate
# directly, we drop down to one of these by intent.
_ABSTRACT_SCENES = {
    "ai": [
        "abstract glowing neural network with flowing particles",
        "geometric data crystals orbiting a central core, soft blue light",
        "minimalist server racks dissolving into light particles",
        "isometric circuit-board landscape with pulsing energy waves",
    ],
    "ml": [
        "graph nodes connecting and pulsing in 3D space",
        "abstract gradient descent visualization, contour lines morphing",
        "data points clustering and recolouring on a dark grid",
    ],
    "crypto": [
        "abstract golden coins orbiting a digital chain",
        "blockchain blocks linking together in a 3D space, neon glow",
        "wireframe network of interconnected wallets, no logos",
    ],
    "trading": [
        "abstract candlestick chart morphing through patterns, dark theme",
        "floating holographic price chart with glowing trendlines",
        "abstract market depth heat-map shifting colours",
    ],
    "default": [
        "abstract flowing geometric shapes, dark gradient background",
        "minimalist line-art knowledge graph forming and reforming",
        "soft particle field with glowing focal points, cinematic",
    ],
}


def sanitize_prompt(prompt: str) -> Tuple[str, list[str]]:
    """Strip risky tokens. Returns (clean_prompt, list_of_removed_patterns)."""
    cleaned = prompt
    removed: list[str] = []
    for pattern in _STRIP_PATTERNS:
        matches = pattern.findall(cleaned)
        if matches:
            removed.extend(m if isinstance(m, str) else " ".join(m) for m in matches)
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-—")
    return cleaned, removed


def _classify_topic(title: str, excerpt: str) -> str:
    text = f"{title} {excerpt}".lower()
    if any(k in text for k in ("trade", "candle", "chart", "indicator", "pattern", "entry")):
        return "trading"
    if any(k in text for k in ("crypto", "defi", "blockchain", "wallet", "token", "coin")):
        return "crypto"
    if any(k in text for k in ("machine learning", "neural net", "deep learning")):
        return "ml"
    if any(k in text for k in ("ai", "agent", "llm", "model", "gpt")):
        return "ai"
    return "default"


def build_safe_prompt(title: str, excerpt: str) -> str:
    """Produce a Seedance-safe prompt regardless of how risky the source
    article's title is. Strategy:
      - sanitize → if anything got stripped, drop to abstract scene
      - if title fails is_safe_topic → drop to abstract scene
      - otherwise compose a cinematic conceptual prompt from the title"""
    sanitized_title, removed = sanitize_prompt(title)
    topic_ok, _ = is_safe_topic(sanitized_title)

    import random
    intent = _classify_topic(title, excerpt)

    if removed or not topic_ok:
        scene = random.choice(_ABSTRACT_SCENES[intent])
        log.info(
            "video_safety.abstract reason=%s scene=%r",
            "stripped" if removed else "unsafe_topic", scene,
        )
        return (
            f"Cinematic vertical short, 9:16. Scene: {scene}. "
            "Subtle motion, dramatic lighting, dark theme, modern editorial style, "
            "no text overlays, no logos, no real people, no brand names."
        )

    return (
        f"Cinematic vertical short, 9:16. Concept: {sanitized_title}. "
        f"Abstract conceptual visualization. "
        "Subtle camera motion, dramatic lighting, dark theme, modern editorial style, "
        "no text overlays, no logos, no real people, no brand names."
    )


def is_safe_hero_url(url: Optional[str]) -> bool:
    """Refuse to use any hero image whose URL points at the WP media-roulette
    range (legacy /uploads/<year>/<month>/<small-numeric>.jpg files) — those
    are old stock photos with people/brands. Only Seedream-generated heroes
    (which have descriptive slugs) are safe for i2v."""
    if not url:
        return False
    # Seedream-generated filenames are descriptive slugs from the article
    # title (e.g. ".../what-is-an-ai-agent-hero.png"). Media-roulette
    # filenames are bare numbers (e.g. ".../8148.jpg").
    filename = url.rsplit("/", 1)[-1]
    stem = filename.rsplit(".", 1)[0]
    if stem.isdigit():
        return False
    if len(stem) < 5:
        return False
    return True
