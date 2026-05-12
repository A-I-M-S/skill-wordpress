from atproto import Client as BC
from dotenv import load_dotenv
from nostr_sdk import Client, NostrSigner, Keys, RelayUrl, EventBuilder
import asyncio, os as o, re, requests as r, time
from pathlib import Path
load_dotenv()

WP_HOST = o.getenv("WP_HOST"); WP_USER = o.getenv("WP_USER"); WP_PW = o.getenv("WP_PW"); CATEGORY_FILE = Path(__file__).resolve().parent / "wordpress-categories.json"

def submit_to_indexnow(a):
    try: r.post("https://api.indexnow.org/indexnow", json={"host": WP_HOST, "key": o.getenv("INDEXNOW_KEY"), "urlList": a}, timeout=10)
    except Exception as e: print(f"[ERROR] IndexNow exception: {e}")

def post_to_linkedin(a: str):
    try: r.post("https://api.linkedin.com/v2/ugcPosts", headers={"Authorization":f"Bearer {o.getenv('LINKEDIN_TOKEN')}","Content-Type":"application/json"}, json={"author":o.getenv("LINKEDIN_AUTHOR"),"lifecycleState":"PUBLISHED","specificContent":{"com.linkedin.ugc.ShareContent":{"shareCommentary":{"text":a},"shareMediaCategory":"NONE"}},"visibility":{"com.linkedin.ugc.MemberNetworkVisibility":"PUBLIC"}})
    except Exception as e: print(f"[ERROR] LinkedIn failed: {e}")

def post_to_threads(a, b):
    try:
        t = f"https://graph.threads.net/v1.0/{o.getenv('THREADS_ID')}/threads"; s = o.getenv("THREADS_TOKEN")
        d = r.post(t, data={"media_type":"IMAGE","image_url":b,"text":a,"access_token":s})
        time.sleep(5); r.post(f"{t}_publish", data={"creation_id":d.json().get("id"),"access_token":s})
    except Exception as e: print(f"[ERROR] Threads failed: {e}")

def post_to_facebook(a):
    try: r.post(f"https://graph.facebook.com/v25.0/{o.getenv('FACEBOOK_PAGE_ID')}/feed", data={'message':a,'access_token':o.getenv("FACEBOOK_TOKEN")})
    except Exception as e: print(f"[ERROR] Facebook failed: {e}")

def post_to_telegram(a):
    try: r.post(f"https://api.telegram.org/bot{o.getenv('TELEGRAM_TOKEN')}/sendMessage", data={"chat_id": o.getenv("TELEGRAM_CHAT_ID"), "text": a, "parse_mode": "HTML", "disable_web_page_preview": False}, timeout=15)
    except Exception as e: print(f"[ERROR] Telegram failed: {e}")

def post_to_discord(a):
    try: r.post(f"https://discord.com/api/v10/channels/{o.getenv('DISCORD_CHANNEL_ID')}/messages", headers={"Authorization": f"Bot {o.getenv('DISCORD_TOKEN')}", "Content-Type": "application/json"}, json={"content": a}, timeout=15)
    except Exception as e: print(f"[ERROR] Discord failed: {e}")

def post_to_bluesky(a, b, c):
    try: d = BC(); d.login(login=o.getenv("BLUESKY_USER"), password=o.getenv("BLUESKY_PASS")); d.send_post(text=a[:300], embed={"$type":"app.bsky.embed.external","external":{"uri":b,"title":a[:50],"description":"Read more","thumb":d.upload_blob(r.get(c).content).blob}})
    except Exception as e: print(f"[ERROR] Bluesky failed: {e}")

def post_to_dev(a, b, c):
    try: r.post("https://dev.to/api/articles", json= {"article": {"title": a, "published": True, "body_markdown": b, "tags": ["News", "Insights", "AI", "Web4.5"], "canonical_url": c}}, headers={"api-key": o.getenv("DEVTO_KEY"), "Content-Type": "application/json"})
    except Exception as e: print(f"[ERROR] DEV failed: {e}")

# def post_to_hashnode(a, b):
#     try:
#         d = r.post("https://gql.hashnode.com", json={"query": "mutation($i:CreateDraftInput!){createDraft(input:$i){draft{id}}}", "variables": {"i": {"title": a, "contentMarkdown": b, "publicationId":o.getenv("HASHNODE_PUBLICATION_ID"), "slug": f"{re.sub(r'-+', '-', re.sub(r'[^a-z0-9-]', '', a.lower().replace(' ', '-'))).strip('-')}-{int(time.time())}"}}}, headers={"Authorization": o.getenv("HASHNODE_TOKEN"), "Content-Type": "application/json"}).json()
#         r.post("https://gql.hashnode.com", json={"query": "mutation($i:PublishDraftInput!){publishDraft(input:$i){post{url}}}", "variables": {"i": {"draftId": d["data"]["createDraft"]["draft"]["id"]}}}, headers={"Authorization": o.getenv("HASHNODE_TOKEN"), "Content-Type": "application/json"}).json()
#     except Exception as e: print(f"[ERROR] Hashnode failed: {e}")

async def nostr_post_async(a):
    try:
        b = Client(NostrSigner.keys(Keys.parse(o.getenv("NOSTR_KEY"))))
        for c in ["wss://relay.damus.io", "wss://nos.lol", "wss://relay.snort.social", "wss://relay.nostr.band", "wss://relay.primal.net"]: await b.add_relay(RelayUrl.parse(c))
        await b.connect(); await asyncio.sleep(1); await b.send_event_builder(EventBuilder.text_note(a[:280]))
    except Exception as e: print(f"[ERROR] Nostr failed: {e}")

def post_to_wordpress_com(a, b):
    try: r.post(f"https://public-api.wordpress.com/rest/v1.1/sites/{o.getenv('WORDPRESS_COM_USERNAME')}.wordpress.com/posts/new", headers={"Authorization": f"Bearer {o.getenv("WORDPRESS_COM_TOKEN")}"}, data={"title": a, "content": b, "status": "publish"})
    except Exception as e: print(f"[ERROR] WordPress.com exception: {e}")