# InsightGinie SEO + Outpush Plan

## Immediate fixes
- Keep Composio-gated growth scripts paused until the GSC, GA4, Sheets, Drive, Docs, Facebook, and YouTube connected accounts are ACTIVE again. `scripts/doctor.py --only composio` now reports exact broken account IDs.
- Do not raise `MAX_POSTS_PER_DAY` above 4. For the current generalist domain, promotion and refreshes beat more net-new posts.
- Keep Reddit and duplicate-content mirrors default-off unless manually reviewed.

## SEO priorities
1. Refresh pages with impressions, CTR below 5%, and average position 6-15 using `scripts/refresh_low_ctr.py` once GSC reconnects.
2. Consolidate near-duplicate posts into stronger hub pages; redirect thin/overlapping articles instead of publishing more variants.
3. Add first-party assets to every new/updated post: tables, TL;DR callouts, calculators, examples, screenshots, or templates.
4. Tighten snippets: title = outcome + audience + specificity; meta = problem + benefit + proof.
5. Add internal links from refreshed posts to one relevant hub and two supporting articles.

## Outpush priorities
1. Re-promote existing high-potential posts across LinkedIn, Bluesky, Threads, Telegram, Discord, and HN approval links.
2. Use platform-native angles rather than one caption everywhere: contrarian LinkedIn hook, concise Threads/Bluesky thread, Telegram summary, HN neutral title.
3. Shorts/Reels cadence: 1/day max after YouTube token + quota are healthy. Treat TikTok as draft-only until access token and app review are done.
4. Track every push in the growth sheet after Google Sheets reconnects.

## Guardrails
- If Seedream hits Safe Experience / inference limits, fallback placeholder images are acceptable for promotion; do not block distribution.
- If YouTube token is missing, fail with auth instructions instead of attempting browser auth from cron/headless jobs.
- If a Composio account is missing/revoked/expired, skip or fail clearly rather than retrying the same broken ID.
