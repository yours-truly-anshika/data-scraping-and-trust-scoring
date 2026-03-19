from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scrapers.youtube_scraper import YouTubeScraper
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled


REQUIRED_RECORD_KEYS = {
    "source_type",
    "source_id",
    "source",
    "metadata",
    "content",
    "content_chunks",
    "medical_disclaimer_presence",
    "has_medical_disclaimer",
    "trust_score",
    "status",
    "error",
}


def main() -> None:
    scraped_path = Path("data/raw/scraped_data.json")
    if not scraped_path.exists():
        raise FileNotFoundError(f"Missing file: {scraped_path}")

    payload = json.loads(scraped_path.read_text(encoding="utf-8"))
    _validate_top_level(payload)
    _validate_records(payload)
    _validate_transcript_disabled_edge_case()
    print("Validation passed: schema and edge-case checks are successful.")


def _validate_top_level(payload: dict[str, Any]) -> None:
    expected_keys = {"blogs", "youtube", "pubmed"}
    missing = expected_keys - set(payload)
    if missing:
        raise AssertionError(f"Top-level keys missing: {sorted(missing)}")

    if not isinstance(payload["blogs"], list):
        raise AssertionError("`blogs` must be a list")
    if not isinstance(payload["youtube"], list):
        raise AssertionError("`youtube` must be a list")
    if not isinstance(payload["pubmed"], dict):
        raise AssertionError("`pubmed` must be an object")


def _validate_records(payload: dict[str, Any]) -> None:
    records: list[dict[str, Any]] = []
    records.extend(payload["blogs"])
    records.extend(payload["youtube"])
    records.append(payload["pubmed"])

    for idx, record in enumerate(records):
        if not isinstance(record, dict):
            raise AssertionError(f"Record #{idx} must be an object")

        missing = REQUIRED_RECORD_KEYS - set(record)
        if missing:
            raise AssertionError(f"Record #{idx} missing keys: {sorted(missing)}")

        if not isinstance(record["metadata"], dict):
            raise AssertionError(f"Record #{idx} metadata must be an object")
        if not isinstance(record["content_chunks"], list):
            raise AssertionError(f"Record #{idx} content_chunks must be an array")
        if not all(isinstance(chunk, str) for chunk in record["content_chunks"]):
            raise AssertionError(f"Record #{idx} content_chunks must contain only strings")

        # Task requirement: trust_score must be float.
        trust_score = record["trust_score"]
        if not isinstance(trust_score, (float, int)) or isinstance(trust_score, bool):
            raise AssertionError(f"Record #{idx} trust_score must be a float-compatible number")


def _validate_transcript_disabled_edge_case() -> None:
    original_fetch = YouTubeTranscriptApi.fetch

    def _fake_fetch(_self: Any, _video_id: str) -> Any:
        raise TranscriptsDisabled("transcripts disabled")

    try:
        YouTubeTranscriptApi.fetch = _fake_fetch
        scraper = YouTubeScraper()
        chunks = scraper._fetch_transcript("dummy-video-id")
        if chunks != ["Transcript unavailable"]:
            raise AssertionError("Transcripts disabled edge-case did not return fallback message")
    finally:
        YouTubeTranscriptApi.fetch = original_fetch


if __name__ == "__main__":
    main()
