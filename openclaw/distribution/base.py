"""Shared payload type for distributors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PostPayload:
    title: str
    excerpt: str
    url: str
    html_content: str
    md_content: str
    tags: List[str]
    image_url: Optional[str] = None

    @property
    def social_text(self) -> str:
        return f"[OpenClaw] {self.title}\n\n{self.excerpt}\n\nRead more: {self.url}"

    @property
    def short_social_text(self) -> str:
        return f"{self.excerpt}\n\n{self.url}"
