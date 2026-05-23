"""Small Composio REST client used by OpenClaw.

Composio keeps OAuth tokens out of this repo. We only store the project API
key, user id, and connected-account ids in .env.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests

from .config import settings
from .logging_utils import log


@dataclass(frozen=True)
class ComposioResult:
    successful: bool
    data: Any = None
    error: Any = None
    log_id: Optional[str] = None


class ComposioClient:
    def __init__(self) -> None:
        cfg = settings.composio
        if not cfg.api_key:
            raise RuntimeError("COMPOSIO_API_KEY is not set")
        if not cfg.user_id:
            raise RuntimeError("COMPOSIO_USER_ID is not set")
        self.base_url = cfg.base_url.rstrip("/")
        self.user_id = cfg.user_id
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": cfg.api_key,
            "accept": "application/json",
            "content-type": "application/json",
        })

    def execute(self, tool_slug: str, *, arguments: Optional[dict[str, Any]] = None,
                connected_account_id: Optional[str] = None, text: Optional[str] = None,
                timeout: int = 90) -> ComposioResult:
        payload: dict[str, Any] = {"user_id": self.user_id}
        if connected_account_id:
            payload["connected_account_id"] = connected_account_id
        if text is not None:
            payload["text"] = text
        else:
            payload["arguments"] = arguments or {}
        try:
            resp = self.session.post(
                f"{self.base_url}/tools/execute/{tool_slug}",
                json=payload,
                timeout=timeout,
            )
            body = resp.json()
        except Exception as exc:
            log.warning("composio.execute transport_err tool=%s err=%s", tool_slug, exc)
            return ComposioResult(False, error=str(exc))
        if resp.status_code >= 400:
            log.warning("composio.execute http_err tool=%s status=%s body=%s", tool_slug, resp.status_code, body)
            return ComposioResult(False, error=body)
        return ComposioResult(
            successful=bool(body.get("successful", False)),
            data=body.get("data"),
            error=body.get("error"),
            log_id=body.get("log_id"),
        )

    def connected_accounts(self) -> list[dict[str, Any]]:
        resp = self.session.get(f"{self.base_url}/connected_accounts", params={"limit": 100, "account_type": "ALL"}, timeout=30)
        resp.raise_for_status()
        return resp.json().get("items", [])


def available() -> bool:
    return settings.composio.enabled
