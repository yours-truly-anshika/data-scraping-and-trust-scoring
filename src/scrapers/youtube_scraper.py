from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, VideoUnavailable

from .base import BaseScraper, ScrapeResult


class YouTubeScraper(BaseScraper):
    def __init__(self, api_key: str | None = None, timeout_seconds: int = 20) -> None:
        self.api_key = api_key or ""
        self.timeout_seconds = timeout_seconds
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

    def scrape(self, source: str) -> ScrapeResult:
        video_id = self._extract_video_id(source)
        metadata = self._fetch_metadata(video_id)
        chunks = self._fetch_transcript(video_id)
        full_text = "\n\n".join(chunks)

        return ScrapeResult(
            source_type="youtube",
            source_id=video_id,
            metadata=metadata,
            content=full_text,
            content_chunks=chunks,
        )

    def _fetch_metadata(self, video_id: str) -> dict[str, Any]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url, headers=self._headers, timeout=self.timeout_seconds)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        title = self._meta_content(soup, "property", "og:title") or self._meta_content(
            soup, "name", "title"
        )
        channel_title = self._extract_channel_title(soup)
        description = self._meta_content(soup, "property", "og:description")
        published_at = self._meta_content(soup, "itemprop", "datePublished") or self._meta_content(
            soup, "itemprop", "uploadDate"
        )
        keywords_raw = self._meta_content(soup, "name", "keywords")
        tags = [tag.strip() for tag in keywords_raw.split(",")] if keywords_raw else []

        # Fallback title from page title if meta is unavailable.
        if not title and soup.title:
            title = soup.title.get_text(strip=True)

        if not title:
            raise ValueError(f"Could not extract metadata from YouTube page for id: {video_id}")

        return {
            "video_id": video_id,
            "url": url,
            "title": title or "",
            "channel_title": channel_title or "",
            "published_date": published_at or "",
            "description": description or "",
            "tags": tags,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "metadata_strategy": "no_key_meta_scrape",
        }

    @staticmethod
    def _meta_content(soup: BeautifulSoup, attr_name: str, attr_value: str) -> str:
        node = soup.find("meta", attrs={attr_name: attr_value})
        if not node:
            return ""
        return str(node.get("content", "")).strip()

    def _extract_channel_title(self, soup: BeautifulSoup) -> str:
        for attr_name, attr_value in (
            ("itemprop", "author"),
            ("name", "author"),
        ):
            value = self._meta_content(soup, attr_name, attr_value)
            if value:
                return value

        link_name = soup.find("link", attrs={"itemprop": "name"})
        if link_name and link_name.get("content"):
            return str(link_name.get("content", "")).strip()

        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text() or ""
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue

            channel = self._extract_author_name_from_jsonld(payload)
            if channel:
                return channel

        return ""

    def _extract_author_name_from_jsonld(self, payload: Any) -> str:
        if isinstance(payload, list):
            for item in payload:
                value = self._extract_author_name_from_jsonld(item)
                if value:
                    return value
            return ""

        if not isinstance(payload, dict):
            return ""

        author = payload.get("author")
        if isinstance(author, dict):
            name = str(author.get("name", "")).strip()
            if name:
                return name
        if isinstance(author, list):
            for item in author:
                if isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                    if name:
                        return name

        graph = payload.get("@graph")
        if graph:
            return self._extract_author_name_from_jsonld(graph)

        return ""

    def _fetch_transcript(self, video_id: str) -> list[str]:
        try:
            transcript_data = YouTubeTranscriptApi().fetch(video_id)
        except (TranscriptsDisabled, VideoUnavailable):
            return ["Transcript unavailable"]
        except Exception as exc:
            raise RuntimeError(f"Transcript retrieval failed for {video_id}: {exc}") from exc

        lines: list[str] = []
        for entry in transcript_data:
            text = str(entry.text).strip()
            if not text:
                continue
            lines.append(text)

        if not lines:
            return ["Transcript unavailable"]

        # Build virtual transcript paragraphs so downstream chunking can
        # preserve local context before sentence-level fallback splitting.
        lines_per_paragraph = 7
        paragraphs: list[str] = []
        for idx in range(0, len(lines), lines_per_paragraph):
            block = lines[idx : idx + lines_per_paragraph]
            paragraph = " ".join(block).strip()
            if paragraph:
                paragraphs.append(paragraph)

        return paragraphs

    @staticmethod
    def _extract_video_id(source: str) -> str:
        if "youtube.com" not in source and "youtu.be" not in source:
            return source

        parsed = urlparse(source)

        if "youtu.be" in parsed.netloc:
            return parsed.path.lstrip("/")

        query = parse_qs(parsed.query)
        video_id = query.get("v", [""])[0]
        if video_id:
            return video_id

        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed"}:
            return path_parts[1]

        raise ValueError(f"Could not determine video id from source: {source}")
