"""Reject topics likely to cause SEO / E-E-A-T / content-moderation pain."""
from __future__ import annotations

import re
from typing import Tuple

# News-event verbs/phrases that indicate "today's news" rather than evergreen.
_NEWS_VERBS = {
    "appoints", "appointed", "resigns", "resigned", "fired", "hired",
    "launches", "launched", "announces", "announced", "unveils", "unveiled",
    "acquires", "acquired", "merges", "merged", "files", "filed", "sues", "sued",
    "wins", "lost", "elected", "indicted", "arrested", "charged",
    "raises", "raised", "closes", "closed", "buys", "bought", "sells", "sold",
    "killed", "dies", "died", "injured", "rescued",
    "joins", "joined", "leaves", "left", "quits", "quit",
    "reports", "reported", "posts", "posted",
    "added", "boosted", "expanded", "improved", "increased",
    "broke", "broken", "hit", "hits", "set", "sets", "surpasses", "surpassed",
    "climbs", "dives", "falls", "soars", "plunges", "drops", "dropped",
    "gains", "gained", "slumps", "jumps", "jumped", "crashes", "crashed",
    "slides", "rallies", "rallied", "tops", "topped", "beats", "beat",
    "misses", "missed", "plummets", "skyrockets",
}

# Known company suffixes — if we see "X Inc" / "X Corp" / "X Bank" / "X LLC"
# treat as a proper-noun brand we should not write about.
_COMPANY_SUFFIXES = {
    "inc", "corp", "corporation", "co", "ltd", "limited", "llc", "plc",
    "bank", "holdings", "group", "ag", "sa", "nv", "kgaa", "bv", "ab",
    "university", "college", "hospital", "ministry", "department",
}

# Title-case honorifics / job titles → real person ahead.
_PERSON_HINTS = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "rev", "sir", "dame", "lord",
    "ceo", "cfo", "coo", "cto", "cmo", "president", "vp", "evp", "svp",
    "chairman", "chairwoman", "chairperson", "director", "founder",
    "senator", "congressman", "congresswoman", "governor", "mayor",
    "minister", "secretary", "ambassador", "judge", "justice",
    "captain", "general", "admiral", "colonel", "lieutenant", "officer",
}

# Geopolitical / regional triggers that often add legal+moderation risk.
_GEO_RISK = {
    "russia", "ukraine", "israel", "palestine", "gaza", "iran", "china",
    "taiwan", "north korea", "syria", "afghanistan", "myanmar",
}

# Generic single-letter / ALL-CAPS tokens to ignore when counting capitals.
_STOPCAPS = {"AI", "ML", "API", "SEO", "LLM", "GPT", "CEO", "USA", "EU", "UK",
             "ETF", "DEFI", "NFT", "DAO", "IPO", "B2B", "B2C", "SAAS"}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9'-]*", text)


def _capitalized_runs(tokens: list[str]) -> list[list[str]]:
    """Return groups of >=2 consecutive capitalized tokens (proper-noun clusters),
    skipping ALL-CAPS acronyms we know are safe."""
    runs: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        is_cap = tok[:1].isupper() and tok.upper() not in _STOPCAPS
        if is_cap:
            current.append(tok)
        else:
            if len(current) >= 2:
                runs.append(current)
            current = []
    if len(current) >= 2:
        runs.append(current)
    return runs


def is_safe_topic(topic: str) -> Tuple[bool, str]:
    """Return (ok, reason). reason is "" when ok."""
    lower = topic.lower()
    tokens = _tokenize(topic)
    if not tokens:
        return False, "empty"
    if len(tokens) < 2:
        return False, "too short"
    if len(tokens) > 18:
        return False, "too long (news-headline shape)"

    # 1. News verbs → news headline, not evergreen
    for tok in tokens:
        if tok.lower() in _NEWS_VERBS:
            return False, f"news verb: {tok!r}"

    # 2. Company / institution suffix → branded entity
    for tok in tokens:
        if tok.lower() in _COMPANY_SUFFIXES:
            return False, f"branded entity suffix: {tok!r}"

    # 3. Person hint → real person
    for tok in tokens:
        if tok.lower() in _PERSON_HINTS:
            return False, f"person hint: {tok!r}"

    # 4. Geopolitical risk
    for risk in _GEO_RISK:
        if risk in lower:
            return False, f"geopolitical risk: {risk!r}"

    # 5. AP-style headline capitalization (most content tokens TitleCased)
    _STOPWORDS = {"of", "the", "and", "in", "on", "at", "for", "to",
                  "a", "an", "by", "with", "from", "as", "or", "but",
                  "vs", "via", "near", "into", "onto"}
    content_tokens = [t for t in tokens if t.lower() not in _STOPWORDS]
    if len(content_tokens) >= 6:
        titled = sum(
            1 for t in content_tokens
            if t[:1].isupper() and t.upper() not in _STOPCAPS
        )
        if titled / len(content_tokens) >= 0.70:
            return False, f"AP-style headline shape ({titled}/{len(content_tokens)} title-cased)"

    # 6. Cluster of capitalized tokens mid-phrase (real proper nouns)
    runs = _capitalized_runs(tokens)
    for run in runs:
        first_idx = tokens.index(run[0])
        if first_idx > 0 and len(run) >= 2:
            return False, f"proper-noun cluster mid-phrase: {' '.join(run)!r}"

    # 7. Digit-heavy strings — "$10M" / "Q3" / specific-year news patterns
    if re.search(r"\$\d", topic) or re.search(r"\bQ[1-4]\b", topic):
        return False, "specific financial number pattern"
    if re.search(r"\b(19|20)\d{2}\b", topic):
        # Year is okay only if accompanied by evergreen markers
        evergreen_marker = re.search(
            r"\b(trends|guide|best|top|review|reviews|cheat|forecast|outlook)\b",
            lower,
        )
        if not evergreen_marker:
            return False, "specific year without evergreen marker"

    return True, ""


def filter_topics(topics: list[str]) -> list[str]:
    """Return only the safe topics from a candidate list."""
    return [t for t in topics if is_safe_topic(t)[0]]
