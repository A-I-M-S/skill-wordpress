from ddgs import DDGS
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
import asyncio, html2text, json, random, os as o, re, requests as r, socialMedia as s, sys
load_dotenv()

def search_trending_topic(a):
    t = a
    try:
        with DDGS() as ddgs: results = list(ddgs.news(query=a, max_results=10))
        if results: t = random.choice(results)["title"]
    except Exception as e: print(f"[WARN] DuckDuckGo news failed: {e}")
    print(f"[INFO] Using topic: {t}")
    return t

def universal_query(topic):
    print("[INFO] Attempting generation")

    prompt = f"""
You are an expert SEO blog writer.
You MUST return ONLY valid JSON.
STRICT RULES:
- Output ONLY raw JSON
- No markdown
- No code blocks
- No explanations
- No extra text before or after JSON
- content MUST be valid clean HTML
- DO NOT use markdown syntax (#, ##, ###, *, -)
- DO NOT include <html> or <body>
- Use semantic HTML tags only:
  <h2>, <h3>, <p>, <ul>, <li>, <strong>
JSON FORMAT:
{{
  "title": "string",
  "excerpt": "string",
  "tags": ["string"],
  "content": "string"
}}
REQUIRED FIELDS:
- title
- excerpt
- tags
- content
CONTENT REQUIREMENTS:
- Write a high-quality SEO-optimized blog post about "{topic}"
- At least 1200 words
- Use <h2> for main sections
- Use <h3> for subsections
- Use <p> for paragraphs
- Use <ul>/<li> for lists
- Use <strong> for important keywords
- Add FAQ section using:
  <h3>Question</h3>
  <p>Answer</p>
Return ONLY valid JSON.
"""
    try:
        payload = {
            "model": "google/gemini-3.1-flash-lite",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": 3000,
            "provider": {"order": ["google-ai-studio"], "allow_fallbacks": False}
        }
        res = r.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {o.getenv('OR_SK')}", "Content-Type": "application/json"},
            json=payload,
            timeout=120
        )
        data = res.json()
        return data['choices'][0]['message']['content']
    except Exception as e: print(f"[ERROR]: {e}\res: {res.text}")

def query_LLM(a):
    b = universal_query(a)
    if not b: raise ValueError("universal_query returned empty response")
    b = b.strip()
    if b.startswith("```"): b = "\n".join(b.split("\n")[1:-1])
    try: return json.loads(b)
    except json.JSONDecodeError: pass
    c = re.search(r'\{.*\}', b, re.DOTALL)
    if c: return json.loads(c.group(0))
    raise ValueError("No valid JSON found")

def get_tag_ids(a):
    tag_ids = []
    for tag in a:
        d = r.get(f"https://{s.WP_HOST}/wp-json/wp/v2/tags?search={tag}", auth=HTTPBasicAuth(s.WP_USER, s.WP_PW))
        results = d.json()
        if results: tag_ids.append(results[0]['id'])
        else: tag_ids.append(r.post(f"https://{s.WP_HOST}/wp-json/wp/v2/tags", auth=HTTPBasicAuth(s.WP_USER, s.WP_PW), headers={"Content-Type": "application/json"}, data=json.dumps({"name": tag})).json()['id'])
    return tag_ids

def main():
    with open(s.CATEGORY_FILE, "r", encoding="utf-8") as f: b = json.load(f)
    c = random.choice(b); post_data=query_LLM(search_trending_topic(c["name"])); 
    if len(sys.argv) > 1: print(post_data)
    else:
        category_id=c["id"]; title = post_data['title']
        media_id = random.choice(range(int(o.getenv("MEDIA_RANGE_START")), int(o.getenv("MEDIA_RANGE_END"))))
        image_url = r.get(f"https://{s.WP_HOST}/wp-json/wp/v2/media/{media_id}", auth=HTTPBasicAuth(s.WP_USER, s.WP_PW)).json().get("source_url")
        d = r.post(f"https://{s.WP_HOST}/wp-json/wp/v2/posts", auth=HTTPBasicAuth(s.WP_USER, s.WP_PW), headers={"Content-Type": "application/json"}, data=json.dumps({"title": title, "content": post_data["content"], "excerpt": post_data.get("excerpt", ""), "status": "publish", "categories": [category_id], "tags": get_tag_ids(post_data.get("tags", [])), "featured_media": media_id}))
        if d.status_code == 201:
            post_url = d.json().get('link')
            content = f"[OpenClaw] {title}\n\n{post_data.get('excerpt', '')}\n\nRead more: {post_url}"
            s_content = f"[OpenClaw] {post_data.get('excerpt', '')}\n\nRead more: {post_url}"
            md_content = html2text.html2text(post_data["content"])
            print(f"[INFO] Post URL: {post_url}")
            s.submit_to_indexnow([post_url])
            s.post_to_linkedin(content);
            s.post_to_threads(content, image_url)
            s.post_to_facebook(content)
            s.post_to_telegram(content)
            s.post_to_discord(content)
            s.post_to_bluesky(content, post_url, image_url)
            s.post_to_dev(title, md_content, post_url)
            # s.post_to_hashnode(title, md_content)
            s.post_to_wordpress_com(title, content)
            asyncio.run(s.nostr_post_async(s_content))
        else: print(f"[ERROR] Failed to publish post. HTTP {d.status_code}: {d.text}")

if __name__ == "__main__":
    main()