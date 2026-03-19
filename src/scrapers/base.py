from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ScrapeResult:
    source_type: str
    source_id: str
    metadata: dict[str, Any]
    content: str
    content_chunks: list[dict[str, Any]]


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self, source: str) -> ScrapeResult:
        """Scrape a single source identifier (URL, video id, PubMed id)."""
