"""Shared Google service-account auth for the analytics stack (GSC, GA4, Sheets).

Drop a service-account JSON at GOOGLE_SERVICE_ACCOUNT_FILE (default
gsc-service-account.json in the project root) and grant the SA email access to:
  - Search Console property (Settings > Users and permissions; Restricted is enough)
  - GA4 property (Admin > Property Access Management; Viewer)
  - the growth Google Sheet (Share the sheet with the SA email; Editor)
All analytics modules skip gracefully until the file is present.
"""
from __future__ import annotations

import os
from typing import Optional, Sequence

from .config import PROJECT_ROOT
from .logging_utils import log

_CRED_CACHE: dict = {}


def service_account_path() -> Optional[str]:
    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or os.getenv(
        "GSC_SERVICE_ACCOUNT_FILE", "gsc-service-account.json"
    )
    if not os.path.isabs(path):
        path = str(PROJECT_ROOT / path)
    return path if os.path.exists(path) else None


def credentials(scopes: Sequence[str]):
    path = service_account_path()
    if not path:
        return None
    key = (path, tuple(scopes))
    if key in _CRED_CACHE:
        return _CRED_CACHE[key]
    try:
        from google.oauth2 import service_account
    except ImportError:
        log.warning("google_auth.skip reason=google_api_libs_missing")
        return None
    creds = service_account.Credentials.from_service_account_file(path, scopes=list(scopes))
    _CRED_CACHE[key] = creds
    return creds


def bearer_token(scopes: Sequence[str]) -> Optional[str]:
    creds = credentials(scopes)
    if not creds:
        return None
    try:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        return creds.token
    except Exception as exc:
        log.warning("google_auth.token err=%s", exc)
        return None
