---
name: skill-wordpress
description: "Automated SEO autoblogging and multi-platform distribution. Generates long-form SEO articles, publishes to WordPress with E-E-A-T enrichment + ByteDance Seedream images, and fans out to LinkedIn, Bluesky, Threads, Facebook, Telegram, Discord, Hashnode, Nostr, Reddit, Hacker News (semi-auto) and YouTube Shorts. Enforces a hard 4-posts/day publishing cap to stay clear of Google's scaled-content-abuse signal."
---

# OpenClaw — SEO Growth Engine (v0.4)

A maintained, package-structured pipeline for AI-driven content + multi-channel distribution. Built with strict velocity guardrails because the legacy 15-min cron (96 posts/day) is the exact pattern Google's Helpful Content system penalises.

## Overview

- AI-generated articles (OpenRouter with fallback chain)
- E-E-A-T injection: real author block, JSON-LD Article schema, internal links
- ByteDance Seedream hero images
- WordPress REST publishing with daily quota + cooldown + duplicate-title guard
- Multi-platform fan-out, each in its own module
- Promote-existing-post mode for back-catalog traffic growth

## Quick start

```bash
pip install -r requirements.txt
cp .env.sample .env       # fill in keys
python3 scripts/publish.py --dry-run    # smoke test
python3 scripts/publish.py              # publish + distribute
python3 scripts/promote.py              # re-share an existing post
python3 scripts/fetch_categories.py     # refresh data/categories.full.json
```

## Recommended cron

```cron
0 */6 * * *   cd /path/to/skill-wordpress && python3 wordpress-automation.py
30 */2 * * *  cd /path/to/skill-wordpress && python3 scripts/promote.py
```

**Do NOT** run more often than every 4–6 hours. The pipeline will refuse to publish above `MAX_POSTS_PER_DAY` (default 4) or before `MIN_MINUTES_BETWEEN_POSTS` (default 240) has elapsed.

## Layout

```
openclaw/        # main package (config, llm, seo, trends, indexing, images, wordpress, distribution)
scripts/         # publish.py, promote.py, fetch_categories.py
data/            # curated_categories.json, categories.full.json
wordpress-automation.py / socialMedia.py   # legacy shims for backward-compat
```

See README.md for the full architecture, Composio setup, distributor matrix, Reddit/HN/YouTube setup, and migration notes.

## Notes

- `data/curated_categories.json` is the niche-restricted category list used by `publish.py`. Edit it to control which categories the autoblogger writes for.
- All env vars are accessed via `openclaw.config.settings` — do not read env from any other module.
- Composio handles Google Search Console, Google Analytics, Google Sheets, Reddit, LinkedIn, and Facebook OAuth. Reddit defaults OFF; YouTube Shorts defaults OFF; WordPress.com mirror and Dev.to stay OFF because they are duplicate-content/account-risk footguns.
