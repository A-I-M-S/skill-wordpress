from ddgs import DDGS
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
import asyncio, html2text, json, random, os as o, re, requests as r
import socialMedia as s
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
    print("[INFO] Attempting Google Gemini...")
    system_prompt = """You are an expert SEO blog writer. You are an API that returns ONLY valid JSON.
STRICT RULES:
- Output ONLY JSON
- content MUST be valid HTML (NO markdown)
- DO NOT use #, *, or markdown syntax
- Use semantic HTML tags: <h2>, <h3>, <p>, <ul>, <li>, <strong>
- Format everything properly for WordPress
- No explanations, no extra text
"""
    user_msg = f"""Write a high-quality, SEO-optimized blog post about "{topic}".
Requirements:
- Content MUST be in clean HTML
- Use <h2> for main sections
- Use <h3> for subsections
- Use <p> for paragraphs
- Use <ul>/<li> for lists
- Use <strong> for important keywords
- Add FAQ section with <h3> questions and <p> answers
- Do NOT use markdown (#, ##, ###, *)
- Do NOT include <html> or <body>
- At least 1200 words
"""
    try:
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "title": {"type": "STRING"},
                        "excerpt": {"type": "STRING"},
                        "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "content": {"type": "STRING"}
                    },
                    "required": ["title", "excerpt", "tags", "content"]
                },
                "maxOutputTokens": 8192
            }
        }
        res = r.post(o.getenv("API_ADDR_3"), json=payload, timeout=120)
        if res.status_code == 200: return res.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        print(f"[ERROR] Fallback & Google exception: {e}")
    payload = {"model": o.getenv("API_MODEL_2"), "messages": [{"role": "system", "content": system_prompt},{"role": "user", "content": user_msg}], "response_format": {"type": "json_object"}}
    res = r.post(f"{o.getenv("API_ADDR_2")}/chat/completions", headers={"Authorization": f"Bearer {o.getenv("API_KEY_2")}"}, json=payload, timeout=600)
    data = res.json()
    if 'choices' in data: return data['choices'][0]['message']['content']
    raise ValueError("Both Google and fallback failed")

def query_LLM(a):
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
        d = r.get(f"https://{s.WP_HOST}/wp-json/wp/v2/tags?search={tag}", auth=HTTPBasicAuth(s.WP_USER, s.WP_PW))
        results = d.json()
        if results: tag_ids.append(results[0]['id'])
        else: tag_ids.append(r.post(f"https://{s.WP_HOST}/wp-json/wp/v2/tags", auth=HTTPBasicAuth(s.WP_USER, s.WP_PW), headers={"Content-Type": "application/json"}, data=json.dumps({"name": tag})).json()['id'])
    return tag_ids

def main():
    with open(s.CATEGORY_FILE, "r", encoding="utf-8") as f: b = json.load(f)
    c = random.choice(b); post_data=query_LLM(search_trending_topic(c["name"])); category_id=c["id"]; title = post_data['title']
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