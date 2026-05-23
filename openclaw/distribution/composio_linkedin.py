"""LinkedIn URL sharing through Composio OAuth."""
from __future__ import annotations

from ..composio_client import ComposioClient, available as composio_available
from ..config import settings
from ..logging_utils import log
from ..social_copy import clean_text, rewrite, utm_url
from .base import PostPayload


def post(payload: PostPayload) -> None:
    if not (composio_available() and settings.composio.linkedin_account_id):
        log.info("composio_linkedin.skip reason=not_configured")
        return
    if not settings.composio.linkedin_author_urn:
        log.info("composio_linkedin.skip reason=no_author_urn")
        return

    url = utm_url(payload.url, source="linkedin")
    commentary = rewrite(payload.title, payload.excerpt, channel="linkedin", url=url)
    args = {
        "author": settings.composio.linkedin_author_urn,
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": commentary[:2800]},
                "shareMediaCategory": "ARTICLE",
                "media": [{
                    "status": "READY",
                    "originalUrl": url,
                    "title": {"text": clean_text(payload.title, 200)},
                    "description": {"text": clean_text(payload.excerpt, 250)},
                }],
            }
        },
    }
    result = ComposioClient().execute(
        "LINKEDIN_CREATE_ARTICLE_OR_URL_SHARE",
        connected_account_id=settings.composio.linkedin_account_id,
        arguments=args,
    )
    if result.successful:
        log.info("composio_linkedin.post ok data=%s", result.data)
    else:
        log.warning("composio_linkedin.post err=%s", result.error)
