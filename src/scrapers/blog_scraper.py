from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, ScrapeResult


class BlogScraper(BaseScraper):
    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

    def scrape(self, source: str) -> ScrapeResult:
        response = requests.get(source, headers=self._headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for tag_name in ("nav", "ads", "footer"):
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Remove common ad containers that are not represented as <ads> tags.
        for ad_candidate in soup.select(
            "[class*='ad'], [id*='ad'], [class*='sponsor'], [id*='sponsor']"
        ):
            ad_candidate.decompose()

        articles = soup.find_all("article")
        chunks: list[dict[str, Any]] = []

        for idx, article in enumerate(articles):
            text = article.get_text(separator=" ", strip=True)
            if text:
                chunks.append({"chunk_id": idx, "text": text})

        if not chunks:
            # Fallback for RSS/XML feeds.
            for idx, item in enumerate(soup.find_all("item")):
                title = item.find("title")
                description = item.find("description")
                text = " ".join(
                    part
                    for part in [
                        title.get_text(" ", strip=True) if title else "",
                        description.get_text(" ", strip=True) if description else "",
                    ]
                    if part
                ).strip()
                if text:
                    chunks.append({"chunk_id": idx, "text": text})

        if not chunks:
            # Final fallback for pages that don't use <article> or RSS item tags.
            lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
            for idx, line in enumerate(lines[:50]):
                chunks.append({"chunk_id": idx, "text": line})

        full_text = "\n\n".join(chunk["text"] for chunk in chunks)
        page_title = soup.title.get_text(strip=True) if soup.title else ""

        return ScrapeResult(
            source_type="blog",
            source_id=source,
            metadata={
                "url": source,
                "title": page_title,
                "article_count": len(chunks),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
            content=full_text,
            content_chunks=chunks,
        )
