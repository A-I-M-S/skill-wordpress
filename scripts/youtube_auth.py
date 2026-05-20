"""Interactive YouTube OAuth helper — headless / SSH friendly.

Run this ONCE (and then again whenever your token expires, which is every
7 days while the OAuth app is in Testing mode).

Two modes:

  TUNNEL MODE (default)
    Starts a callback listener on a FIXED port (8089 by default; override
    with YOUTUBE_AUTH_PORT). You forward that port from your laptop with:

        ssh -L 8089:localhost:8089 <user>@<your-server>

    Then click the URL this script prints — your laptop browser hits
    localhost:8089, which is tunneled to the server where this script
    is listening. Works for any number of re-auths.

  MANUAL MODE (--manual)
    Zero networking required. Script prints an auth URL, you open it on
    any browser, complete the consent, then paste the FULL redirect URL
    (it will show in the browser address bar after consent — even if the
    page itself shows a "connection refused" error, the URL is what
    matters) back into the prompt. The script extracts the `code` and
    exchanges it for tokens.

Usage:
    python3 scripts/youtube_auth.py             # tunnel mode
    python3 scripts/youtube_auth.py --manual    # paste-back mode
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw.config import settings  # noqa: E402
from openclaw.logging_utils import get_logger  # noqa: E402

log = get_logger("yt-auth")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def _ensure_deps() -> None:
    try:
        import google_auth_oauthlib  # noqa: F401
        import google.oauth2.credentials  # noqa: F401
        import googleapiclient  # noqa: F401
    except ImportError:
        sys.exit(
            "Missing dependencies. Install with:\n"
            "    pip install google-api-python-client google-auth-oauthlib"
        )


def _save_creds(creds, token_file: Path) -> None:
    token_file.write_text(creds.to_json())
    print(f"\n  Token saved -> {token_file}")


def _verify(creds) -> None:
    """Hit channels.list to confirm the token actually works."""
    from googleapiclient.discovery import build  # type: ignore
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        print("  WARN: no YouTube channel on this Google account.")
        return
    ch = items[0]
    print(f"  Channel: {ch['snippet']['title']}")
    print(f"  Subscribers: {ch['statistics'].get('subscriberCount', '?')}")
    print(f"  Videos:      {ch['statistics'].get('videoCount', '?')}")


def tunnel_mode(secrets_file: Path, token_file: Path, port: int) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore

    print("=" * 72)
    print("YOUTUBE OAUTH — TUNNEL MODE")
    print("=" * 72)
    print("\nOn your LAPTOP (not this server), run:\n")
    print(f"    ssh -L {port}:localhost:{port} <user>@<this-server>\n")
    print("Leave that SSH session open. Then come back here and continue.")
    input("\nPress Enter when the tunnel is up... ")

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), SCOPES)
    print(f"\nListening on port {port}. Open the URL below in your laptop browser:\n")
    creds = flow.run_local_server(
        port=port,
        open_browser=False,
        access_type="offline",
        prompt="consent",
    )
    _save_creds(creds, token_file)
    _verify(creds)


def manual_mode(secrets_file: Path, token_file: Path) -> None:
    from google_auth_oauthlib.flow import Flow  # type: ignore

    print("=" * 72)
    print("YOUTUBE OAUTH — MANUAL PASTE MODE")
    print("=" * 72)

    flow = Flow.from_client_secrets_file(
        str(secrets_file),
        scopes=SCOPES,
        redirect_uri="http://localhost",  # any localhost works; we paste it back
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    print("\n1. Open this URL in any browser (laptop, phone, anywhere):\n")
    print(f"   {auth_url}\n")
    print("2. Complete consent. You'll be redirected to a URL that starts with")
    print("   http://localhost/?... and your browser will show a 'site can't be")
    print("   reached' error. THAT IS FINE. Copy the full URL from the")
    print("   address bar.\n")
    pasted = input("3. Paste the full redirect URL here: ").strip()

    qs = urllib.parse.urlparse(pasted).query
    params = urllib.parse.parse_qs(qs)
    if "error" in params:
        sys.exit(f"\nOAuth error: {params['error'][0]}")
    if "code" not in params:
        sys.exit("\nCould not find ?code=... in the pasted URL. Try again.")

    code = params["code"][0]
    print("\nExchanging code for tokens...")
    flow.fetch_token(code=code)
    creds = flow.credentials
    _save_creds(creds, token_file)
    _verify(creds)


def main() -> int:
    ap = argparse.ArgumentParser(description="YouTube OAuth helper (headless-friendly).")
    ap.add_argument("--manual", action="store_true",
                    help="Paste-back mode (no networking on this host needed).")
    ap.add_argument("--port", type=int,
                    default=int(__import__("os").environ.get("YOUTUBE_AUTH_PORT", "8089")),
                    help="Callback port for tunnel mode (default 8089).")
    args = ap.parse_args()

    _ensure_deps()

    cfg = settings.youtube
    secrets_file = Path(cfg.client_secrets_file)
    token_file = Path(cfg.token_file)

    if not secrets_file.exists():
        sys.exit(
            f"Client secrets not found: {secrets_file}\n"
            "Download from Google Cloud Console -> Credentials -> your OAuth\n"
            "client -> 'Download JSON', and save to that path."
        )

    if token_file.exists():
        print(f"NOTE: existing token at {token_file} will be overwritten.")
        ans = input("Continue? [y/N] ").strip().lower()
        if ans != "y":
            return 1

    if args.manual:
        manual_mode(secrets_file, token_file)
    else:
        tunnel_mode(secrets_file, token_file, args.port)

    print("\nDone. Verify with:  python3 scripts/doctor.py --only youtube")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
