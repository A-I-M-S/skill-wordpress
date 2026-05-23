# OpenClaw — WordPress SEO Growth Engine

Automated SEO content generation, WordPress publishing, Search Console refreshes, analytics feedback, and safe multi-channel distribution for InsightGinie.

OpenClaw is intentionally conservative: it prioritizes improving existing pages and promoting useful answers over high-volume autopublishing. That is the safer path under Google's helpful-content and scaled-content policies.

---

## Core workflows

| Workflow | Command | Purpose |
|---|---|---|
| Hourly orchestrator | `python3 scripts/orchestrate.py` | Cron entrypoint; decides what should run this hour. |
| Publish one new post | `python3 scripts/publish.py` | Generate, SEO-enrich, publish to WordPress, then distribute. |
| Promote existing post | `python3 scripts/promote.py` | Re-share an existing article without creating new content. |
| Refresh low-CTR pages | `python3 -m scripts.refresh_low_ctr` | Use Search Console opportunities to improve existing posts. |
| SEO dashboard sync | `python3 -m scripts.growth_dashboard` | Write GSC, GA4, and referral data into Google Sheets. |
| Shorts pipeline | `python3 scripts/shorts.py` | Create and upload short-form video when enabled. |
| Health checks | `python3 scripts/doctor.py` | Validate credentials and integration readiness. |

---

## Composio-first integrations

Composio OAuth is the preferred integration layer for tools that otherwise require fragile app credentials.

Currently wired:

- Google Search Console — query/page opportunities, URL inspection, sitemap signals.
- Google Analytics 4 — page and referral performance.
- Google Sheets — SEO growth dashboard.
- Reddit — OAuth posting through Composio; no internal Reddit app keys needed.
- LinkedIn — Composio URL/article shares when configured.
- Facebook — Composio Page posts when configured.
- Google Drive / Docs / YouTube — connected for future workflows.

Required Composio env vars:

```env
COMPOSIO_API_KEY=
COMPOSIO_USER_ID=
COMPOSIO_GSC_ACCOUNT_ID=
COMPOSIO_REDDIT_ACCOUNT_ID=
COMPOSIO_GOOGLE_ANALYTICS_ACCOUNT_ID=
COMPOSIO_GOOGLESHEETS_ACCOUNT_ID=
COMPOSIO_LINKEDIN_ACCOUNT_ID=
COMPOSIO_FACEBOOK_ACCOUNT_ID=
GSC_SITE_URL=https://insightginie.com/
GA4_PROPERTY=properties/486401787
GROWTH_SHEET_ID=
LINKEDIN_AUTHOR_URN=
FACEBOOK_PAGE_ID=
```

Reddit no longer needs `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, or `REDDIT_PASSWORD`. Keep only the safety controls:

```env
DIST_REDDIT=false
REDDIT_ALLOWED_SUBS=u_aloycwl
REDDIT_MIN_INTERVAL_MIN=240
```

Leave `DIST_REDDIT=false` until the target communities are manually reviewed. When enabled, the code posts text-first Reddit submissions with a source link and UTM tracking, not blind link drops.

---

## Project layout

```text
skill-wordpress/
├── openclaw/
│   ├── config.py                 # all env vars and typed settings
│   ├── composio_client.py        # small Composio REST client
│   ├── gsc.py                    # Search Console opportunities via Composio
│   ├── analytics.py              # GA4 page/referral metrics via Composio
│   ├── growth_sheet.py           # Google Sheets dashboard writer
│   ├── article_builder.py        # research/write/polish article generation
│   ├── seo.py                    # schema, internal links, E-E-A-T helpers
│   ├── indexing.py               # IndexNow + Bing submission
│   ├── wordpress/                # WordPress REST client and publisher
│   ├── images/                   # Seedream image generation
│   ├── video/                    # Seedance video generation
│   └── distribution/             # social distribution modules
├── scripts/
│   ├── orchestrate.py            # cron entrypoint
│   ├── publish.py                # create and publish one new article
│   ├── promote.py                # promote an existing article
│   ├── refresh_low_ctr.py        # GSC-driven refresh workflow
│   ├── growth_dashboard.py       # GSC + GA4 -> Google Sheets
│   ├── cleanup.py                # artifact cleanup
│   └── doctor.py                 # integration checks
├── data/                         # categories and keyword state
├── artifacts/                    # generated media and local state; ignored
├── logs/                         # runtime logs; ignored
├── wordpress-automation.py       # legacy shim
├── socialMedia.py                # legacy shim
├── requirements.txt
└── .env.sample
```

---

## Quick start

```bash
pip install -r requirements.txt
cp .env.sample .env
python3 scripts/doctor.py
python3 scripts/orchestrate.py --what
python3 -m scripts.growth_dashboard
python3 scripts/publish.py --dry-run
```

The live cron uses the hourly orchestrator:

```cron
0 * * * * cd /home/openclaw/skill-wordpress && /usr/bin/python3 scripts/orchestrate.py >> /home/openclaw/skill-wordpress/logs/wp.log 2>&1
```

Make sure `logs/` exists before cron runs.

---

## SEO strategy

1. **Measure first** — Search Console finds pages with impressions but poor CTR/rank.
2. **Refresh existing winners** — improve titles, meta descriptions, missing sections, and internal links.
3. **Create selectively** — new posts stay capped by `MAX_POSTS_PER_DAY` and `MIN_MINUTES_BETWEEN_POSTS`.
4. **Distribute carefully** — LinkedIn/Facebook/Bluesky/Threads/etc. are allowed; Reddit stays opt-in and allowlisted.
5. **Track outcomes** — GA4 referrals and page metrics flow into the Google Sheet dashboard.

Useful commands:

```bash
python3 -m scripts.growth_dashboard --days 28 --gsc-limit 200
python3 -m scripts.refresh_low_ctr --limit 3 --dry-run
python3 -m scripts.refresh_low_ctr --limit 3
python3 scripts/promote.py --url https://insightginie.com/example/
```

---

## Publishing guardrails

Default settings:

```env
MAX_POSTS_PER_DAY=4
MIN_MINUTES_BETWEEN_POSTS=240
TITLE_SIM_THRESHOLD=0.80
```

Do not raise these casually. For this site, refreshing and promoting the back catalog is more valuable than publishing many new articles.

---

## Distribution channels

| Channel | Default | Auth path | Notes |
|---|---:|---|---|
| LinkedIn | on | Composio preferred; direct token fallback | Best organic fit for AI/tech/business articles. |
| Facebook | on | Composio preferred; direct token fallback | Requires a Page id. |
| Reddit | off | Composio only | Enable only after subreddit review and allowlist setup. |
| Bluesky | on | direct app password | Good low-friction distribution. |
| Threads | on | direct token | Image/link distribution. |
| Telegram | on | bot token | Also useful for approval notifications. |
| Discord | on | bot token | Useful only when relevant communities exist. |
| Hacker News | on | semi-automated link | No official posting API; requires human approval. |
| YouTube Shorts | off | Google OAuth file/token | Optional video growth loop. |
| WordPress.com mirror | off | deprecated | Duplicate-content risk. |
| Dev.to | off | deprecated | Account-ban risk on automated content. |

---

## ByteDance image/video generation

Seedream generates article and promo images. Seedance can create short video clips for the Shorts pipeline.

```env
SEEDREAM_API_KEY=
SEEDREAM_ENDPOINT=https://ark.ap-southeast.bytepluses.com/api/v3/images/generations
SEEDREAM_MODEL=seedream-5-0-260128
SEEDANCE_API_KEY=
SEEDANCE_ENDPOINT=https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks
SEEDANCE_MODEL=dreamina-seedance-2-0-fast-260128
```

If these are missing, the core WordPress/GSC/GA4 workflows still run.

---

## Operational notes

- All environment access should go through `openclaw.config.settings`.
- Do not store provider API secrets in committed files.
- `artifacts/`, `logs/`, `.env`, and OAuth token files are ignored.
- Use Composio for OAuth tools whenever possible; avoid creating platform-specific app keys unless needed.
- Run `python3 scripts/doctor.py` after changing credentials.
- Check runtime logs with `tail -n 100 logs/wp.log`.

---

## Legacy shims

`wordpress-automation.py` and `socialMedia.py` remain for backwards compatibility, but new workflows should call the `scripts/` entrypoints directly.
