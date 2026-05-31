"""Multi-pass article generation: research → draft → polish.

The single-shot generate_article() in llm.py produces shallow derivative
content — exactly what Google's Helpful Content System down-ranks. This
builder does three LLM calls instead:

  1. RESEARCH pass — given a keyword, output a structured outline:
        - search intent (informational / transactional / commercial)
        - 5-7 H2 section titles
        - 3-5 specific facts/claims per section (bullet, not prose)
        - 5-8 FAQ questions readers would ask
        - 2-3 internal-link anchor suggestions

  2. DRAFT pass — given the outline, write the full article body.
     Structured HTML with H2/H3/p/ul/blockquote; ~1400-1800 words.
     Includes the FAQ section as a proper <section> with q/a pairs so
     SEO.build_faq_schema() can pick it up.

  3. POLISH pass — given the draft, rewrite the title for CTR (60 chars
     max, includes the primary keyword near the front), generate a
     150-160 char meta description, and produce 5-8 tags.

Each pass is independently retried via the model fallback chain.
Total cost: roughly 3x a single-shot generation. The quality jump (real
H2 structure, FAQ, internal-link anchors, CTR-optimized title) is the
single biggest content-quality improvement available — and the FAQ
alone gives you FAQPage schema rich-result eligibility.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .llm import LLMClient, GeneratedArticle
from .logging_utils import log


# ---- data shapes ----------------------------------------------------------

@dataclass
class Outline:
    topic: str
    intent: str               # "informational" | "transactional" | "commercial"
    primary_keyword: str
    sections: List[dict] = field(default_factory=list)  # [{"h2": str, "facts": [str]}]
    faqs: List[dict] = field(default_factory=list)       # [{"q": str, "a_hint": str}]
    internal_anchors: List[str] = field(default_factory=list)
    original_asset: dict = field(default_factory=dict)
    trust_notes: List[str] = field(default_factory=list)


# ---- prompts --------------------------------------------------------------

RESEARCH_PROMPT = """You are an SEO content strategist. Given a target keyword,
produce a structured outline for a 1500-word evergreen article that targets
that keyword.

Return ONLY a JSON object with this exact shape:
{{
  "intent": "informational" | "transactional" | "commercial",
  "primary_keyword": "<the exact keyword from the brief>",
  "sections": [
    {{"h2": "<section title>", "facts": ["fact 1", "fact 2", "fact 3"]}}
  ],
  "faqs": [
    {{"q": "<question a real reader would ask>",
      "a_hint": "<one-sentence hint on what the answer should cover>"}}
  ],
  "internal_anchors": ["<short anchor text>", "..."],
  "original_asset": {{"type": "checklist|comparison_table|worked_example|decision_tree|mini_framework",
                     "description": "<specific useful asset to include>"}},
  "trust_notes": ["<source or verification note>", "..."]
}}

Constraints:
- 5 to 7 sections.
- Each section has 3-5 short factual bullets (not prose).
- 5-8 FAQs that real searchers would ask (PAA-style).
- 3-5 internal_anchors — short phrases (2-5 words) that we could use to
  link FROM other articles ON OUR SITE TO this one.
- Choose a concrete angle; do not produce a generic encyclopedia article.
- Include one original_asset readers can use immediately.
- Add trust_notes for claims that should be verified; do not invent citations, statistics, or named sources.
- Avoid boilerplate phrases such as "ultimate guide", "comprehensive guide",
  "complete guide", "unlocking", "in today's digital landscape", and
  "start your journey today".
- Do NOT mention specific real companies, products, or people by name unless
  they are essential and widely verifiable. Stay mostly evergreen.

Keyword: {keyword}

Return ONLY the JSON object. No prose, no markdown fences."""

DRAFT_PROMPT = """You are an experienced technical writer producing an SEO-
optimized evergreen article. Use the outline below to write the full
article body in semantic HTML.

Requirements:
- 1600-2200 words total.
- Open with a 80-120 word lead paragraph that includes the primary
  keyword in the first sentence and states the article's concrete angle.
- Each section becomes an <h2> with the exact title given. Inside, write
  3-6 short paragraphs and use <ul>/<ol>/<blockquote> where natural.
- Include the requested original_asset as an HTML table, checklist, worked
  example, or decision tree; make it specific enough that a reader can use it.
- Add a short <h2>Editorial Notes</h2> section with verification caveats for
  finance, health, legal, trading, security, or fast-changing technical claims.
- After the last content section, add a single <section class="faq">
  containing an <h2>Frequently Asked Questions</h2> followed by each FAQ
  as <h3>{{question}}</h3><p>{{answer in 40-80 words}}</p>.
- Do NOT include <html>, <head>, <body>, or <title> tags.
- Do NOT invent statistics, citations, quotes, or named sources.
- Avoid boilerplate phrases such as "ultimate guide", "comprehensive guide",
  "complete guide", "unlocking", "in today's digital landscape", and
  "start your journey today".
- Plain HTML only — no markdown.

Outline:
{outline_json}

Return ONLY the HTML body. No prose before or after."""

POLISH_PROMPT = """Read the article HTML below and return ONLY a JSON object
with this exact shape:

{{
  "title": "<58-char-max SEO title; primary keyword near the front; no
            year unless it's strongly evergreen-relevant; avoid Guide/Ultimate/Comprehensive>",
  "excerpt": "<140-158 char meta description; specific benefit, no generic CTA>",
  "tags": ["<5-8 SEO tags; lowercase; relevant>"]
}}

Primary keyword: {keyword}

Article HTML:
{html}

Banned title/excerpt phrases: ultimate guide, comprehensive guide, complete guide, unlocking, master, mastering, start today, read our full guide.
Return ONLY the JSON object."""


# ---- engine ---------------------------------------------------------------

def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def _parse_json(raw: str) -> dict:
    return json.loads(_strip_fences(raw))


def build_outline(llm: LLMClient, keyword: str) -> Outline:
    raw = llm.complete_text(
        RESEARCH_PROMPT.format(keyword=keyword),
        max_tokens=1200,
    )
    if not raw:
        raise RuntimeError("LLM research pass returned empty")
    data = _parse_json(raw)
    outline = Outline(
        topic=keyword,
        intent=data.get("intent", "informational"),
        primary_keyword=data.get("primary_keyword", keyword),
        sections=data.get("sections", []),
        faqs=data.get("faqs", []),
        internal_anchors=data.get("internal_anchors", []),
        original_asset=data.get("original_asset", {}),
        trust_notes=data.get("trust_notes", []),
    )
    log.info(
        "article.research ok intent=%s sections=%d faqs=%d",
        outline.intent, len(outline.sections), len(outline.faqs),
    )
    return outline


def build_draft(llm: LLMClient, outline: Outline) -> str:
    raw = llm.complete_text(
        DRAFT_PROMPT.format(outline_json=json.dumps(
            {
                "primary_keyword": outline.primary_keyword,
                "intent": outline.intent,
                "sections": outline.sections,
                "faqs": outline.faqs,
                "original_asset": outline.original_asset,
                "trust_notes": outline.trust_notes,
            },
            indent=2,
        )),
        max_tokens=4000,
    )
    if not raw:
        raise RuntimeError("LLM draft pass returned empty")
    html = _strip_fences(raw)
    log.info("article.draft ok len=%d", len(html))
    return html


def polish(llm: LLMClient, html: str, keyword: str) -> dict:
    raw = llm.complete_text(
        POLISH_PROMPT.format(keyword=keyword, html=html[:6000]),
        max_tokens=400,
    )
    if not raw:
        raise RuntimeError("LLM polish pass returned empty")
    meta = _parse_json(raw)
    log.info(
        "article.polish ok title=%r tags=%d",
        meta.get("title"), len(meta.get("tags", [])),
    )
    return meta


def build_article(topic: str) -> GeneratedArticle:
    """End-to-end: research → draft → polish. Returns GeneratedArticle."""
    llm = LLMClient()
    outline = build_outline(llm, topic)
    html = build_draft(llm, outline)
    meta = polish(llm, html, outline.primary_keyword)
    title = re.sub(r"\b(The\s+)?(Ultimate|Comprehensive|Complete) Guide to\s+", "", meta.get("title", topic), flags=re.I).strip()
    excerpt = re.sub(r"\b(read our full guide|start your journey today|start today)\b[.! ]*", "", meta.get("excerpt", ""), flags=re.I).strip()
    return GeneratedArticle(
        title=title[:70].rstrip(" -|:,."),
        excerpt=excerpt[:158].rstrip(" -|:,."),
        tags=[t.lower().strip() for t in meta.get("tags", []) if t.strip()][:8],
        content=html,
    )
