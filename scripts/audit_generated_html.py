"""Audit recent generated posts for common SEO regressions."""
from __future__ import annotations

import argparse
import re
import sys
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openclaw.wordpress.client import WordPressClient  # noqa: E402

BAD_PATTERNS = [
    ("nested_anchor_in_title_attr", re.compile(r'title=["\']\s*<a\s+', re.I)),
    ("nested_anchor", re.compile(r"<a\b[^>]*>[^<]*<a\b", re.I | re.S)),
    ("generic_generated_alt", re.compile(r'alt=["\']\s*(generated image|image|blog image)\s*["\']', re.I)),
]


def strip_tags(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("rendered", "")
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit recent posts for generated HTML issues.")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    wp = WordPressClient()
    failures: list[str] = []
    page = 1
    checked = 0
    while checked < args.limit:
        posts = wp.list_posts(page=page, per_page=min(100, args.limit - checked), _fields="id,title,link,content,excerpt")
        if not posts:
            break
        for post in posts:
            checked += 1
            html = post.get("content", {}).get("rendered", "")
            title = strip_tags(post.get("title", ""))
            for label, pattern in BAD_PATTERNS:
                if pattern.search(html):
                    failures.append(f"{label}: post={post.get('id')} {post.get('link')} title={title!r}")
            if len(title) > 85:
                failures.append(f"long_title: post={post.get('id')} len={len(title)} {post.get('link')}")
        page += 1
    for failure in failures:
        print(failure)
    print(f"checked={checked} failures={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
