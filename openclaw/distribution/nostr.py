from __future__ import annotations

import asyncio
import os

from nostr_sdk import Client, EventBuilder, Keys, NostrSigner, RelayUrl

from ..logging_utils import log
from .base import PostPayload

RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.snort.social",
    "wss://relay.nostr.band",
    "wss://relay.primal.net",
]


async def _post_async(text: str) -> None:
    key = os.getenv("NOSTR_KEY")
    if not key:
        log.info("nostr.skip reason=no_credentials")
        return
    try:
        client = Client(NostrSigner.keys(Keys.parse(key)))
        for relay in RELAYS:
            await client.add_relay(RelayUrl.parse(relay))
        await client.connect()
        await asyncio.sleep(1)
        await client.send_event_builder(EventBuilder.text_note(text[:280]))
        log.info("nostr.post ok")
    except Exception as exc:
        log.warning("nostr.post err=%s", exc)


def post(payload: PostPayload) -> None:
    asyncio.run(_post_async(payload.short_social_text))
