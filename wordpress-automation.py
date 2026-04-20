from atproto import Client
from ddgs import DDGS
from dotenv import load_dotenv
from nostr_sdk import *
from pathlib import Path
from requests.auth import HTTPBasicAuth
import asyncio
import html2text
import json
import random
import os as o
import re
import requests as r
import sys
import time
load_dotenv()

if sys.argv[1] == "2": API_KEY = o.getenv("API_KEY_2"); API_ADDR = o.getenv("API_ADDR_2"); API_MODEL = o.getenv("API_MODEL_2")
elif sys.argv[1] == "3": API_ADDR = o.getenv("API_ADDR_3")
else: API_KEY = o.getenv("API_KEY_1"); API_ADDR = o.getenv("API_ADDR_1"); API_MODEL = o.getenv("API_MODEL_1")
WP_HOST = o.getenv("WP_HOST"); WP_USER = o.getenv("WP_USER"); WP_PW = o.getenv("WP_PW"); CATEGORY_FILE = Path(__file__).resolve().parent / "wordpress-categories.json"

def search_trending_topic(a):
    t = a
    try:
        with DDGS() as ddgs: results = list(ddgs.news(query=a, max_results=10))
        if results: t = random.choice(results)["title"]
    except Exception as e: print(f"[WARN] DuckDuckGo news failed: {e}")
    print(f"[INFO] Using topic: {t}")
    return t

def universal_query(a):
    print(f"[INFO] Generation attempt")
    system_prompt = """You are an expert SEO blog writer. You are an API that returns ONLY valid JSON.
        STRICT RULES:
        - Output ONLY JSON
        - No explanations
        - No markdown
        - No text before or after JSON
        - No code fences
        """
    user_msg = f"""
        Write a high-quality, SEO-optimized blog post about "{a}".
        Requirements:
        - Write a compelling, click-worthy title
        - Include a clear introduction, structured sections (H2/H3), and conclusion
        - Use bullet points and lists where helpful
        - Add a FAQ section at the end
        - Avoid generic or repetitive content
        - Provide useful insights, examples, or comparisons
        SEO:
        - Naturally include keyword variations
        - Optimize for readability and search intent
        Output STRICT valid JSON only with this schema:
        {{"title": "SEO optimized title","excerpt": "under 160 characters","tags": ["tag1","tag2","tag3"],"content": "HTML article at least 1200 words"}}

        Do not include markdown, explanations, or code fences.
        """
    if sys.argv[1] == "3":
        payload = {"contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_msg}"}]}], "generationConfig": {"response_mime_type": "application/json"}}
        d = r.post(API_ADDR, json=payload, timeout=600)
        return d.json()['candidates'][0]['content']['parts'][0]['text']
    else:
        payload = {"model": API_MODEL, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}]}
        payload["response_format"] = {"type": "json_object"}
        d = r.post(f"{API_ADDR}/chat/completions", headers={"Authorization": f"Bearer {API_KEY}"}, json=payload, timeout=600)
        return d.json()['choices'][0]['message']['content']

def query_trinity(a):
    b = universal_query(a).strip()
    if b.startswith("```"): b = "\n".join(b.split("\n")[1:-1])
    try: return json.loads(b)
    except json.JSONDecodeError: pass
    c = re.search(r'\{.*\}', b, re.DOTALL)
    if c: return json.loads(c.group(0))
    raise ValueError("No valid JSON found")

def get_tag_ids(a):
    tag_ids = []
    for tag in a:
        d = r.get(f"https://{WP_HOST}/wp-json/wp/v2/tags?search={tag}", auth=HTTPBasicAuth(WP_USER, WP_PW))
        results = d.json()
        if results: tag_ids.append(results[0]['id'])
        else: tag_ids.append(r.post(f"https://{WP_HOST}/wp-json/wp/v2/tags", auth=HTTPBasicAuth(WP_USER, WP_PW), headers={"Content-Type": "application/json"}, data=json.dumps({"name": tag})).json()['id'])
    return tag_ids

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
    try: d = Client(); d.login(o.getenv("BLUESKY_USER"), o.getenv("BLUESKY_PASS")); d.send_post(text=a[:300], embed={"$type":"app.bsky.embed.external","external":{"uri":b,"title":a[:50],"description":"Read more","thumb":d.upload_blob(r.get(c).content).blob}})
    except Exception as e: print(f"[ERROR] Bluesky failed: {e}")

def post_to_dev(a, b, c):
    try: r.post("https://dev.to/api/articles", json= {"article": {"title": a, "published": True, "body_markdown": b, "tags": ["News", "Insights", "AI", "Web4.5"], "canonical_url": c}}, headers={"api-key": o.getenv("DEVTO_KEY"), "Content-Type": "application/json"})
    except Exception as e: print(f"[ERROR] DEV failed: {e}")

def post_to_hashnode(a, b):
    try:
        d = r.post("https://gql.hashnode.com", json={"query": "mutation($i:CreateDraftInput!){createDraft(input:$i){draft{id}}}", "variables": {"i": {"title": a, "contentMarkdown": b, "publicationId":o.getenv("HASHNODE_PUBLICATION_ID"), "slug": f"{re.sub(r'-+', '-', re.sub(r'[^a-z0-9-]', '', a.lower().replace(' ', '-'))).strip('-')}-{int(time.time())}"}}}, headers={"Authorization": o.getenv("HASHNODE_TOKEN"), "Content-Type": "application/json"}).json()
        r.post("https://gql.hashnode.com", json={"query": "mutation($i:PublishDraftInput!){publishDraft(input:$i){post{url}}}", "variables": {"i": {"draftId": d["data"]["createDraft"]["draft"]["id"]}}}, headers={"Authorization": o.getenv("HASHNODE_TOKEN"), "Content-Type": "application/json"}).json()
    except Exception as e: print(f"[ERROR] Hashnode failed: {e}")

async def nostr_post_async(a):
    try:
        b = Client(NostrSigner.keys(Keys.parse(o.getenv("NOSTR_KEY"))))
        for c in ["wss://relay.damus.io", "wss://nos.lol", "wss://relay.snort.social", "wss://relay.nostr.band", "wss://relay.primal.net"]: await b.add_relay(RelayUrl.parse(c))
        await b.connect(); await asyncio.sleep(1); await b.send_event_builder(EventBuilder.text_note(a[:280]))
    except Exception as e: print(f"[ERROR] Nostr failed: {e}")

def post_to_wordpress_com(a, b):
    try: r.post(f"https://public-api.wordpress.com/rest/v1.1/sites/{o.getenv('WORDPRESS_COM_USERNAME')}.wordpress.com/posts/new", headers={"Authorization": f"Bearer {o.getenv("WORDPRESS_COM_TOKEN")}"}, data={"title": a, "content": b, "status": "publish"})
    except Exception as e: print(f"[ERROR] WordPress.com exception: {e}")

def main():
    with open(CATEGORY_FILE, "r", encoding="utf-8") as f: b = json.load(f)
    c = random.choice(b); post_data=query_trinity(search_trending_topic(c["name"])); category_id=c["id"]; title = post_data['title']
    media_id = random.choice(range(int(o.getenv("MEDIA_RANGE_START")), int(o.getenv("MEDIA_RANGE_END"))))
    image_url = r.get(f"https://{WP_HOST}/wp-json/wp/v2/media/{media_id}", auth=HTTPBasicAuth(WP_USER, WP_PW)).json().get("source_url")
    d = r.post(f"https://{WP_HOST}/wp-json/wp/v2/posts", auth=HTTPBasicAuth(WP_USER, WP_PW), headers={"Content-Type": "application/json"}, data=json.dumps({"title": title, "content": post_data["content"], "excerpt": post_data.get("excerpt", ""), "status": "publish", "categories": [category_id], "tags": get_tag_ids(post_data.get("tags", [])), "featured_media": media_id}))
    if d.status_code == 201:
        post_url = d.json().get('link')
        content = f"[OpenClaw] {title}\n\n{post_data.get('excerpt', '')}\n\nRead more: {post_url}"
        s_content = f"[OpenClaw] {post_data.get('excerpt', '')}\n\nRead more: {post_url}"
        md_content = html2text.html2text(post_data["content"])
        print(f"[INFO] Post URL: {post_url}")
        submit_to_indexnow([post_url])
        post_to_linkedin(content);
        post_to_threads(content, image_url)
        post_to_facebook(content)
        post_to_telegram(content)
        post_to_discord(content)
        post_to_bluesky(content, post_url, image_url)
        post_to_dev(title, md_content, post_url)
        post_to_hashnode(title, md_content)
        post_to_wordpress_com(title, content)
        asyncio.run(nostr_post_async(s_content))
    else: print(f"[ERROR] Failed to publish post. HTTP {d.status_code}: {d.text}")

if __name__ == "__main__":
    main()