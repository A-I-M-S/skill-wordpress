"""Hashnode publishing. Sets canonical URL → InsightGinie to avoid duplicate-content."""
from __future__ import annotations

import os
import time

import requests

from ..logging_utils import log
from ..seo import slugify
from .base import PostPayload


def post(payload: PostPayload) -> None:
    token = os.getenv("HASHNODE_TOKEN")
    pub_id = os.getenv("HASHNODE_PUBLICATION_ID")
    if not (token and pub_id):
        log.info("hashnode.skip reason=no_credentials")
        return
    slug = f"{slugify(payload.title)}-{int(time.time())}"
    try:
        draft = requests.post(
            "https://gql.hashnode.com",
            json={
                "query": "mutation($i:CreateDraftInput!){createDraft(input:$i){draft{id}}}",
                "variables": {
                    "i": {
                        "title": payload.title,
                        "contentMarkdown": payload.md_content,
                        "publicationId": pub_id,
                        "slug": slug,
                        "originalArticleURL": payload.url,  # canonical
                        "tags": [{"name": t, "slug": slugify(t)} for t in payload.tags[:5]],
                    }
                },
            },
            headers={"Authorization": token, "Content-Type": "application/json"},
            timeout=30,
        ).json()
        draft_id = draft["data"]["createDraft"]["draft"]["id"]
        requests.post(
            "https://gql.hashnode.com",
            json={
                "query": "mutation($i:PublishDraftInput!){publishDraft(input:$i){post{url}}}",
                "variables": {"i": {"draftId": draft_id}},
            },
            headers={"Authorization": token, "Content-Type": "application/json"},
            timeout=30,
        )
        log.info("hashnode.post ok title=%r", payload.title)
    except Exception as exc:
        log.warning("hashnode.post err=%s", exc)
