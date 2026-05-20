"""Read-only credential & connectivity doctor for OpenClaw.

Probes every configured service with the lightest possible authenticated
call and prints a tidy status table. Never posts, never drafts, never
generates a paid image or video.

Usage:
    python3 scripts/doctor.py              # one-line per service
    python3 scripts/doctor.py --verbose    # show full error tracebacks
    python3 scripts/doctor.py --json       # machine-readable JSON output
    python3 scripts/doctor.py --only wp,telegram,youtube   # subset

Exit code:
    0  all configured services OK
    1  at least one configured service failed
       (services explicitly disabled / unconfigured are SKIP and do not
        cause a non-zero exit)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import requests
from requests.auth import HTTPBasicAuth

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw.config import settings  # noqa: E402
from openclaw.logging_utils import get_logger  # noqa: E402

log = get_logger("doctor")

OK, FAIL, SKIP = "OK", "FAIL", "SKIP"


@dataclass
class Result:
    name: str
    status: str
    detail: str = ""
    error: Optional[str] = None
    elapsed_ms: int = 0


# ---------------------------------------------------------------------------
# Individual checks. Each returns (status, detail).
# ---------------------------------------------------------------------------

def check_wordpress() -> tuple[str, str]:
    cfg = settings.wp
    if not (cfg.host and cfg.user and cfg.password):
        return SKIP, "WP_HOST / WP_USER / WP_PW not set"
    url = f"{cfg.api_base}/users/me?context=edit"
    r = requests.get(url, auth=HTTPBasicAuth(cfg.user, cfg.password), timeout=15)
    r.raise_for_status()
    me = r.json()
    return OK, f"user={me.get('slug', '?')} role={(me.get('roles') or ['?'])[0]} host={cfg.host}"


def check_openrouter() -> tuple[str, str]:
    key = settings.llm.openrouter_key
    if not key:
        return SKIP, "OR_SK not set"
    r = requests.get(
        "https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {key}"},
        timeout=15,
    )
    r.raise_for_status()
    data = (r.json() or {}).get("data", {})
    limit = data.get("limit")
    usage = data.get("usage", 0)
    label = data.get("label", "")
    parts = []
    if label:
        parts.append(f"key={label}")
    if limit is not None:
        parts.append(f"usage=${usage:.3f}/${limit:.2f}")
    else:
        parts.append(f"usage=${usage:.3f}")
    parts.append(f"model={settings.llm.primary_model}")
    return OK, " ".join(parts)


def check_seedream() -> tuple[str, str]:
    """Seedream has no whoami endpoint. Validate key presence and shape only —
    avoids charging the user just to test config. A real generation will be
    exercised the first time publish.py runs."""
    cfg = settings.seedream
    if not cfg.api_key:
        return SKIP, "SEEDREAM_API_KEY not set"
    if len(cfg.api_key) < 20:
        return FAIL, f"SEEDREAM_API_KEY looks too short ({len(cfg.api_key)} chars)"
    return OK, f"key present model={cfg.model} size={cfg.size}"


def check_seedance() -> tuple[str, str]:
    """Same logic as Seedream — no whoami, just key shape."""
    cfg = settings.seedance
    if not cfg.api_key:
        return SKIP, "SEEDANCE_API_KEY not set"
    if len(cfg.api_key) < 20:
        return FAIL, f"SEEDANCE_API_KEY looks too short ({len(cfg.api_key)} chars)"
    return OK, f"key present model={cfg.model} {cfg.resolution} {cfg.ratio} {cfg.duration}s"


def check_telegram() -> tuple[str, str]:
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token:
        return SKIP, "TELEGRAM_TOKEN not set"
    r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
    r.raise_for_status()
    me = r.json().get("result", {})
    detail = f"bot=@{me.get('username', '?')} (id={me.get('id')})"
    if chat_id:
        chat = requests.get(
            f"https://api.telegram.org/bot{token}/getChat",
            params={"chat_id": chat_id},
            timeout=10,
        )
        if chat.ok:
            c = chat.json().get("result", {})
            detail += f" chat={c.get('title') or c.get('username') or chat_id}"
        else:
            return FAIL, f"{detail} but TELEGRAM_CHAT_ID={chat_id} unreachable"
    else:
        detail += " (no chat_id set)"
    return OK, detail


def check_discord() -> tuple[str, str]:
    token = os.getenv("DISCORD_TOKEN")
    channel = os.getenv("DISCORD_CHANNEL_ID")
    if not token:
        return SKIP, "DISCORD_TOKEN not set"
    r = requests.get(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bot {token}"},
        timeout=10,
    )
    r.raise_for_status()
    me = r.json()
    detail = f"bot={me.get('username')}#{me.get('discriminator')}"
    if channel:
        ch = requests.get(
            f"https://discord.com/api/v10/channels/{channel}",
            headers={"Authorization": f"Bot {token}"},
            timeout=10,
        )
        if ch.ok:
            detail += f" channel=#{ch.json().get('name', '?')}"
        else:
            return FAIL, f"{detail} but channel {channel} unreachable (bot not in server?)"
    return OK, detail


def check_linkedin() -> tuple[str, str]:
    token = os.getenv("LINKEDIN_TOKEN")
    author = os.getenv("LINKEDIN_AUTHOR")
    if not token:
        return SKIP, "LINKEDIN_TOKEN not set"
    # /v2/userinfo works for both OpenID Connect and legacy r_liteprofile scopes
    r = requests.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if r.status_code == 401:
        return FAIL, "401 — token expired or invalid"
    r.raise_for_status()
    info = r.json()
    detail = f"user={info.get('name', info.get('sub', '?'))}"
    if not author:
        detail += " (LINKEDIN_AUTHOR not set)"
    return OK, detail


def check_threads() -> tuple[str, str]:
    token = os.getenv("THREADS_TOKEN")
    tid = os.getenv("THREADS_ID")
    if not (token and tid):
        return SKIP, "THREADS_TOKEN / THREADS_ID not set"
    r = requests.get(
        f"https://graph.threads.net/v1.0/me",
        params={"fields": "id,username", "access_token": token},
        timeout=15,
    )
    r.raise_for_status()
    me = r.json()
    return OK, f"user=@{me.get('username', '?')} id={me.get('id', '?')}"


def check_facebook() -> tuple[str, str]:
    token = os.getenv("FACEBOOK_TOKEN")
    page = os.getenv("FACEBOOK_PAGE_ID")
    if not (token and page):
        return SKIP, "FACEBOOK_TOKEN / FACEBOOK_PAGE_ID not set"
    r = requests.get(
        f"https://graph.facebook.com/v19.0/{page}",
        params={"fields": "id,name,fan_count", "access_token": token},
        timeout=15,
    )
    r.raise_for_status()
    p = r.json()
    return OK, f"page={p.get('name')} (id={p.get('id')}, fans={p.get('fan_count', '?')})"


def check_bluesky() -> tuple[str, str]:
    user = os.getenv("BLUESKY_USER")
    pw = os.getenv("BLUESKY_PASS")
    if not (user and pw):
        return SKIP, "BLUESKY_USER / BLUESKY_PASS not set"
    r = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={"identifier": user, "password": pw},
        timeout=15,
    )
    r.raise_for_status()
    s = r.json()
    return OK, f"handle=@{s.get('handle', user)} did={s.get('did', '?')[:24]}..."


def check_nostr() -> tuple[str, str]:
    key = os.getenv("NOSTR_PRIVATE_KEY") or os.getenv("NOSTR_NSEC")
    if not key:
        return SKIP, "NOSTR_PRIVATE_KEY / NOSTR_NSEC not set"
    # Validate format: 64-char hex or bech32 nsec1...
    if re.fullmatch(r"[0-9a-fA-F]{64}", key):
        return OK, "hex key, length OK"
    if key.startswith("nsec1") and len(key) > 60:
        return OK, "bech32 nsec, length OK"
    return FAIL, "key does not look like 64-hex or nsec1..."


def check_hashnode() -> tuple[str, str]:
    token = os.getenv("HASHNODE_TOKEN")
    pub = os.getenv("HASHNODE_PUBLICATION_ID")
    if not token:
        return SKIP, "HASHNODE_TOKEN not set"

    url = "https://gql.hashnode.com"
    query = {"query": "{ me { id username } }"}

    def _attempt(auth_value: str) -> tuple[int, str, Optional[dict]]:
        r = requests.post(
            url,
            headers={"Authorization": auth_value, "Content-Type": "application/json"},
            json=query,
            timeout=15,
        )
        try:
            body = r.json()
        except json.JSONDecodeError:
            body = None
        return r.status_code, r.text[:150], body

    status, body, payload = _attempt(token)
    if status == 401:
        status, body, payload = _attempt(f"Bearer {token}")
    if status != 200:
        return FAIL, f"HTTP {status}: {body}"
    if not payload:
        return FAIL, "empty 200 response"
    if payload.get("errors"):
        return FAIL, f"GraphQL error: {payload['errors'][0].get('message')}"
    me = payload.get("data", {}).get("me", {})
    detail = f"user=@{me.get('username', '?')}"
    if not pub:
        detail += " (HASHNODE_PUBLICATION_ID not set — will skip Hashnode)"
    return OK, detail


def check_reddit() -> tuple[str, str]:
    cfg = settings.reddit
    if not (cfg.client_id and cfg.client_secret and cfg.username and cfg.password):
        return SKIP, "Reddit credentials not set (see Responsible Builder Policy)"
    try:
        import praw  # type: ignore
    except ImportError:
        return FAIL, "praw not installed — pip install praw"
    reddit = praw.Reddit(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        username=cfg.username,
        password=cfg.password,
        user_agent=cfg.user_agent,
        check_for_async=False,
    )
    me = reddit.user.me()
    if me is None:
        return FAIL, "Auth returned None — likely 2FA enabled or app not 'script' type"
    return OK, f"user=u/{me.name} karma={me.link_karma + me.comment_karma} allowed={cfg.allowed_subs}"


def check_indexnow() -> tuple[str, str]:
    key = settings.indexnow_key
    host = settings.wp.host
    if not (key and host):
        return SKIP, "INDEXNOW_KEY / WP_HOST not set"
    r = requests.get(f"https://{host}/{key}.txt", timeout=10)
    if r.status_code != 200:
        return FAIL, f"https://{host}/{key}.txt returned {r.status_code} (key file missing on host)"
    if r.text.strip() != key:
        return FAIL, f"key file content does not match INDEXNOW_KEY"
    return OK, f"key file verified at https://{host}/{key}.txt"


def check_youtube() -> tuple[str, str]:
    cfg = settings.youtube
    if not cfg.enabled:
        return SKIP, "YOUTUBE_ENABLED=false"
    secrets = Path(cfg.client_secrets_file)
    if not secrets.exists():
        return FAIL, f"client secrets not found: {secrets}"
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
    except ImportError:
        return FAIL, "pip install google-api-python-client google-auth-oauthlib"

    scopes = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube.readonly"]
    token_file = Path(cfg.token_file)
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request  # type: ignore
            creds.refresh(Request())
            token_file.write_text(creds.to_json())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets), scopes)
        creds = flow.run_local_server(port=0, open_browser=False)
        token_file.write_text(creds.to_json())

    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        return FAIL, "API call OK but no channel on this account"
    ch = items[0]
    snip = ch["snippet"]; stats = ch["statistics"]
    return OK, (f"channel={snip['title']} subs={stats.get('subscriberCount', '?')} "
                f"videos={stats.get('videoCount', '?')}")


def check_hn() -> tuple[str, str]:
    if not settings.hn.enabled:
        return SKIP, "HN_ENABLED=false"
    notify_chat = settings.hn.notify_chat_id or os.getenv("TELEGRAM_CHAT_ID")
    token = os.getenv("TELEGRAM_TOKEN")
    if not token or not notify_chat:
        return SKIP, "needs Telegram (HN delivers approval link via TG bot)"
    r = requests.get(
        f"https://api.telegram.org/bot{token}/getChat",
        params={"chat_id": notify_chat},
        timeout=10,
    )
    if not r.ok:
        return FAIL, f"approval chat {notify_chat} not reachable by bot"
    c = r.json().get("result", {})
    return OK, f"approval chat={c.get('title') or c.get('username') or notify_chat}"


# ---------------------------------------------------------------------------
# Registry + runner
# ---------------------------------------------------------------------------

CHECKS: List[tuple[str, Callable[[], tuple[str, str]]]] = [
    ("wp",         check_wordpress),
    ("llm",        check_openrouter),
    ("seedream",   check_seedream),
    ("seedance",   check_seedance),
    ("telegram",   check_telegram),
    ("discord",    check_discord),
    ("linkedin",   check_linkedin),
    ("threads",    check_threads),
    ("facebook",   check_facebook),
    ("bluesky",    check_bluesky),
    ("nostr",      check_nostr),
    ("reddit",     check_reddit),
    ("hn",         check_hn),
    ("indexnow",   check_indexnow),
    ("youtube",    check_youtube),
]


def run(only: Optional[set[str]], verbose: bool) -> List[Result]:
    results: List[Result] = []
    for name, fn in CHECKS:
        if only and name not in only:
            continue
        t0 = time.perf_counter()
        try:
            status, detail = fn()
            results.append(Result(name=name, status=status, detail=detail,
                                  elapsed_ms=int((time.perf_counter() - t0) * 1000)))
        except requests.HTTPError as e:
            body = e.response.text[:200] if e.response is not None else ""
            results.append(Result(
                name=name, status=FAIL,
                detail=f"HTTP {e.response.status_code if e.response is not None else '?'}: {body}",
                error=traceback.format_exc() if verbose else None,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
            ))
        except Exception as e:  # noqa: BLE001
            results.append(Result(
                name=name, status=FAIL,
                detail=f"{type(e).__name__}: {e}",
                error=traceback.format_exc() if verbose else None,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
            ))
    return results


def print_table(results: List[Result]) -> None:
    # ANSI colors (no extra deps).
    BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
    GREEN, YELLOW, RED = "\033[32m", "\033[33m", "\033[31m"
    color = {OK: GREEN, FAIL: RED, SKIP: YELLOW}

    name_w = max(len("service"), max(len(r.name) for r in results))
    print(f"\n{BOLD}{'service'.ljust(name_w)}  status  ms     detail{RESET}")
    print(f"{DIM}{'-' * name_w}  ------  -----  {'-' * 60}{RESET}")
    for r in results:
        c = color.get(r.status, "")
        print(f"{r.name.ljust(name_w)}  {c}{r.status.ljust(6)}{RESET}  "
              f"{str(r.elapsed_ms).rjust(5)}  {r.detail}")
        if r.error:
            for line in r.error.rstrip().splitlines():
                print(f"{DIM}    {line}{RESET}")

    ok = sum(1 for r in results if r.status == OK)
    fail = sum(1 for r in results if r.status == FAIL)
    skip = sum(1 for r in results if r.status == SKIP)
    print(f"\n{BOLD}summary{RESET}: {GREEN}{ok} ok{RESET}  "
          f"{RED}{fail} fail{RESET}  {YELLOW}{skip} skip{RESET}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="OpenClaw credentials doctor.")
    ap.add_argument("--verbose", action="store_true",
                    help="Show full tracebacks for failures.")
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON instead of a table.")
    ap.add_argument("--only", default="",
                    help="Comma-separated subset of checks (e.g. wp,telegram,youtube)")
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    if only:
        unknown = only - {name for name, _ in CHECKS}
        if unknown:
            print(f"Unknown check(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            print(f"Available: {', '.join(name for name, _ in CHECKS)}", file=sys.stderr)
            return 2

    results = run(only, verbose=args.verbose)

    if args.json:
        print(json.dumps(
            [{"name": r.name, "status": r.status, "detail": r.detail,
              "elapsed_ms": r.elapsed_ms} for r in results],
            indent=2))
    else:
        print_table(results)

    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
