"""Channel-specific copy helpers for safe distribution."""
from __future__ import annotations

import re

import requests

from .config import settings
from .logging_utils import log


def clean_text(text: str, limit: int | None = None) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip() if limit else text


def utm_url(url: str, *, source: str, medium: str = "social", campaign: str = "openclaw_growth") -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source={source}&utm_medium={medium}&utm_campaign={campaign}"


def rewrite(title: str, excerpt: str, *, channel: str, url: str | None = None) -> str:
    fallback = f"{title}\n\n{clean_text(excerpt, 220)}"
    api_key = settings.llm.openrouter_key
    if not api_key:
        return fallback
    prompts = {
        "linkedin": "Write a polished LinkedIn post. 3 short paragraphs, useful and non-hype. No hashtags unless highly relevant, max 2.",
        "facebook": "Write a friendly Facebook Page post. 2 short paragraphs, clear hook, no clickbait.",
        "reddit": "Write a Reddit self-post that answers the problem first. Be transparent that the linked article is yours if you include the link. No marketing language.",
        "generic": "Write a concise social post. Conversational, helpful, no hype.",
    }
    prompt = (
        f"{prompts.get(channel, prompts['generic'])}\n"
        "Return raw text only.\n\n"
        f"Title: {title}\nExcerpt: {excerpt}\nURL: {url or ''}"
    )
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": settings.llm.primary_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 350,
            },
            timeout=60,
        )
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return text or fallback
    except Exception as exc:
        log.warning("social_copy.rewrite err=%s", exc)
        return fallback
