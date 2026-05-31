"""Facebook Page posting through Composio OAuth."""
from __future__ import annotations

from ..composio_client import ComposioClient, available as composio_available
from ..config import settings
from ..logging_utils import log
from ..social_copy import rewrite, utm_url
from .base import PostPayload


def post(payload: PostPayload) -> bool:
    if not (composio_available() and settings.composio.facebook_account_id):
        log.info("composio_facebook.skip reason=not_configured")
        return False
    if not settings.composio.facebook_page_id:
        log.info("composio_facebook.skip reason=no_page_id")
        return False

    url = utm_url(payload.url, source="facebook")
    message = rewrite(payload.title, payload.excerpt, channel="facebook", url=url)
    result = ComposioClient().execute(
        "FACEBOOK_CREATE_POST",
        connected_account_id=settings.composio.facebook_account_id,
        arguments={
            "page_id": settings.composio.facebook_page_id,
            "message": message[:5000],
            "link": url,
            "published": True,
        },
    )
    if result.successful:
        log.info("composio_facebook.post ok data=%s", result.data)
        return True
    log.warning("composio_facebook.post err=%s", result.error)
    return False
