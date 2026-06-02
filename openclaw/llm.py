"""Multi-provider LLM client with structured-output parsing and fallback."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from .config import settings
from .logging_utils import log

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class GeneratedArticle:
    title: str
    excerpt: str
    tags: List[str]
    content: str  # raw HTML

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "GeneratedArticle":
        return cls(
            title=str(payload.get("title", "")).strip(),
            excerpt=str(payload.get("excerpt", "")).strip(),
            tags=[str(t).strip() for t in payload.get("tags", []) if str(t).strip()],
            content=str(payload.get("content", "")).strip(),
        )


SEO_PROMPT_TEMPLATE = """
You are an expert SEO writer focused on E-E-A-T (Experience, Expertise,
Authoritativeness, Trustworthiness). You MUST return ONLY valid JSON —
no markdown, no code fences, no preamble.

JSON SCHEMA:
{{
  "title": "string (55-65 chars, search-intent, no clickbait emojis)",
  "excerpt": "string (140-160 chars, includes primary keyword)",
  "tags": ["string", ...],   // 4-8 specific tags
  "content": "string"        // semantic HTML, see rules
}}

CONTENT RULES:
- Topic: "{topic}"
- Audience: technically-literate readers (developers, founders, traders).
- Minimum {min_words} words, maximum {max_words} words.
- First paragraph hooks with a concrete fact or statistic.
- Use semantic HTML only: <h2>, <h3>, <p>, <ul>, <li>, <strong>, <em>, <blockquote>.
- DO NOT include <html>, <body>, markdown syntax, or code fences.
- DO NOT include the title in the body — WordPress renders it separately.
- 4-6 <h2> sections; each section has 2-4 <p> paragraphs.
- Add a short FAQ section near the end with 3-4 <h3>Question</h3><p>Answer</p> pairs.
- Cite 2-3 authoritative outbound sources inline using <a href="...">anchor text</a>.
- Mention real entities (companies, papers, people) when relevant.
- End with a <p><strong>Bottom line:</strong> ...</p> takeaway.

Return ONLY the JSON object.
"""


class LLMClient:
    def __init__(self) -> None:
        self.api_key = settings.llm.openrouter_key
        self.primary = settings.llm.primary_model
        self.fallbacks = settings.llm.fallback_models
        self.max_tokens = settings.llm.max_tokens

    def _call(self, model: str, prompt: str) -> Optional[str]:
        if not self.api_key:
            raise RuntimeError("OR_SK (OpenRouter key) not set")
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": self.max_tokens,
        }
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            log.warning("llm.call model=%s err=%s", model, exc)
            return None

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:-1])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in LLM response")
        return json.loads(match.group(0))

    def complete_text(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Plain-text completion across the model fallback chain. Returns ''
        if every model fails. Use for cap"""
        attempts: List[str] = [self.primary, *self.fallbacks]
        for model in attempts:
            payload: Dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens or self.max_tokens,
            }
            try:
                response = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=180,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"].get("content") or ""
                if content.strip():
                    log.info("llm.complete ok model=%s tokens=%s chars=%d", model, max_tokens or self.max_tokens, len(content))
                    return content
                log.warning("llm.complete empty model=%s status=%s", model, response.status_code)
            except Exception as exc:
                detail = ""
                response_obj = locals().get("response")
                if response_obj is not None:
                    detail = f" status={response_obj.status_code} body={response_obj.text[:300]!r}"
                log.warning("llm.complete model=%s err=%s%s", model, exc, detail)
        return ""

    def generate_article(self, topic: str) -> GeneratedArticle:
        prompt = SEO_PROMPT_TEMPLATE.format(
            topic=topic,
            min_words=settings.llm.min_words,
            max_words=settings.llm.min_words + 800,
        )
        attempts: List[str] = [self.primary, *self.fallbacks]
        last_err: Optional[Exception] = None
        for model in attempts:
            raw = self._call(model, prompt)
            if not raw:
                continue
            try:
                data = self._parse_json(raw)
                article = GeneratedArticle.from_dict(data)
                if not article.title or not article.content:
                    raise ValueError("Empty title or content")
                log.info("llm.generate ok model=%s title=%r", model, article.title)
                return article
            except Exception as exc:
                last_err = exc
                log.warning("llm.parse model=%s err=%s", model, exc)
        raise RuntimeError(f"All LLM providers failed. Last error: {last_err}")
