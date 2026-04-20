import requests as r
import json
import os as o
from dotenv import load_dotenv

load_dotenv()

WP_HOST = o.getenv("WP_HOST")
OUTPUT_FILE = "wordpress-categories.json"

def fetch_categories():
    categories = []
    page = 1

    while True:
        url = f"https://{WP_HOST}/wp-json/wp/v2/categories?per_page=100&page={page}"
        response = r.get(url, timeout=30)

        if response.status_code != 200:
            print(f"[ERROR] Failed to fetch page {page}: {response.status_code} {response.text}")
            break

        data = response.json()
        if not data:
            break

        for cat in data:
            categories.append({
                "id": cat["id"],
                "name": cat["name"]
            })

        page += 1

    return categories

def main():
    if not WP_HOST:
        print("[ERROR] WP_HOST not set in .env")
        return

    categories = fetch_categories()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(categories, f, indent=2)

    print(f"[INFO] Saved {len(categories)} categories to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()