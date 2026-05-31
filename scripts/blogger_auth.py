"""Authorize Blogger OAuth and discover the configured Blogspot blog."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

from openclaw.config import settings  # noqa: E402
from openclaw.distribution.blogger import SCOPES  # noqa: E402

STATE_FILE = Path(settings.blogger.token_file).with_suffix(".oauth_state.json")


def _write_env(key: str, value: str) -> None:
    env_path = Path(".env")
    text = env_path.read_text() if env_path.exists() else ""
    lines = text.splitlines()
    out = []
    found = False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    env_path.write_text("\n".join(out) + "\n")


def _new_flow() -> InstalledAppFlow:
    flow = InstalledAppFlow.from_client_secrets_file(settings.blogger.client_secrets_file, SCOPES)
    flow.redirect_uri = "http://localhost"
    return flow


def print_auth_url() -> int:
    flow = _new_flow()
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    STATE_FILE.write_text(json.dumps({
        "state": state,
        "code_verifier": getattr(flow, "code_verifier", None),
        "redirect_uri": flow.redirect_uri,
    }))
    print(url)
    print(f"\nAfter approving, run: python3 -m scripts.blogger_auth --redirect-url 'http://localhost/?state=...&code=...'")
    return 0


def exchange_redirect(redirect_url: str) -> int:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    if not STATE_FILE.exists():
        raise SystemExit("OAuth state file missing. Run python3 -m scripts.blogger_auth --auth-url first.")
    state_data = json.loads(STATE_FILE.read_text())
    params = parse_qs(urlparse(redirect_url).query)
    if params.get("state", [None])[0] != state_data.get("state"):
        raise SystemExit("OAuth state mismatch. Generate a fresh auth URL and approve that exact URL.")
    flow = _new_flow()
    if state_data.get("code_verifier"):
        flow.code_verifier = state_data["code_verifier"]
    flow.oauth2session.scope = None
    flow.fetch_token(authorization_response=redirect_url)
    creds = flow.credentials
    Path(settings.blogger.token_file).write_text(creds.to_json())
    Path(settings.blogger.token_file).chmod(0o600)

    service = build("blogger", "v3", credentials=creds, cache_discovery=False)
    blogs = service.blogs().listByUser(userId="self").execute().get("items", [])
    target = None
    for blog in blogs:
        if settings.blogger.blog_url and settings.blogger.blog_url.rstrip("/") == blog.get("url", "").rstrip("/"):
            target = blog
            break
    if not target and blogs:
        target = blogs[0]
    if target:
        _write_env("BLOGGER_BLOG_ID", target["id"])
        print(f"Blogger token saved. Blog: {target.get('name')} {target.get('url')} id={target['id']}")
    else:
        print("Blogger token saved, but no blogs were returned for this account.")
    STATE_FILE.unlink(missing_ok=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth-url", action="store_true", help="print a new OAuth approval URL and save PKCE state")
    ap.add_argument("--redirect-url", help="the final http://localhost redirect URL after approval")
    args = ap.parse_args()
    if args.redirect_url:
        return exchange_redirect(args.redirect_url)
    return print_auth_url()


if __name__ == "__main__":
    raise SystemExit(main())
