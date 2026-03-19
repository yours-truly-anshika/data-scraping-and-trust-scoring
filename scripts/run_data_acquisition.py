from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scrapers import BlogScraper, PubMedScraper, YouTubeScraper
from src.scoring import score_from_metadata
from src.utils import has_medical_disclaimer


BLOG_TARGETS = [
    "https://techcrunch.com/feed/",
    "https://medium.com/feed/topic/health",
    "https://r.jina.ai/http://www.mayoclinic.org/healthy-lifestyle",
]

YOUTUBE_TARGETS = [
    "aircAruvnKk",
    "1-NxodiGPCU",
]

PUBMED_TARGET = "32720662"

REQUIRED_RECORD_KEYS = [
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
]


def main() -> None:
    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "scraped_data.json"

    results: dict[str, Any] = {
        "blogs": [],
        "youtube": [],
        "pubmed": None,
    }

    blog_scraper = BlogScraper()
    for url in BLOG_TARGETS:
        results["blogs"].append(_run_scrape(blog_scraper, url))

    youtube_scraper = YouTubeScraper()
    for video_source in YOUTUBE_TARGETS:
        results["youtube"].append(_run_scrape(youtube_scraper, video_source))

    ncbi_email = os.getenv("NCBI_EMAIL", "student@example.com").strip()
    ncbi_api_key = os.getenv("NCBI_API_KEY", "").strip() or None
    pubmed_scraper = PubMedScraper(email=ncbi_email, api_key=ncbi_api_key)
    results["pubmed"] = _run_scrape(pubmed_scraper, PUBMED_TARGET)

    output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    # Backward-compatible artifact name for prior steps.
    (output_dir / "acquisition_results.json").write_text(
        json.dumps(results, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote acquisition output to: {output_file}")


def _run_scrape(scraper: Any, source: str) -> dict[str, Any]:
    source_type = _infer_source_type(scraper)
    record = _empty_record(source_type=source_type, source=source)

    try:
        result = scraper.scrape(source)
        payload = asdict(result)
        content_chunks = _normalize_content_chunks(payload.get("content_chunks", []))
        content = str(payload.get("content", "") or "")
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

        medical_disclaimer_presence = has_medical_disclaimer(content_chunks)
        trust_score = _compute_trust_score(
            source_type=str(payload.get("source_type", source_type) or source_type),
            source_id=str(payload.get("source_id", source) or source),
            metadata=metadata,
            content=content,
            content_chunks=content_chunks,
            medical_disclaimer_presence=medical_disclaimer_presence,
        )

        record.update(
            {
                "source_type": str(payload.get("source_type", source_type) or source_type),
                "source_id": str(payload.get("source_id", source) or source),
                "source": source,
                "metadata": metadata,
                "content": content,
                "content_chunks": content_chunks,
                "medical_disclaimer_presence": medical_disclaimer_presence,
                "has_medical_disclaimer": medical_disclaimer_presence,
                "trust_score": float(trust_score),
                "status": "ok",
                "error": None,
            }
        )
        return _ensure_record_keys(record)
    except Exception as exc:  # pragma: no cover
        record["status"] = "error"
        record["error"] = str(exc)
        return _ensure_record_keys(record)


def _infer_source_type(scraper: Any) -> str:
    name = scraper.__class__.__name__.lower()
    if "youtube" in name:
        return "youtube"
    if "pubmed" in name:
        return "pubmed"
    return "blog"


def _normalize_content_chunks(chunks: Any) -> list[str]:
    if not isinstance(chunks, list):
        return []

    normalized: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            text = str(chunk.get("text", "") or "").strip()
        else:
            text = str(chunk or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _compute_trust_score(
    source_type: str,
    source_id: str,
    metadata: dict[str, Any],
    content: str,
    content_chunks: list[str],
    medical_disclaimer_presence: bool,
) -> float:
    published_year = metadata.get("pub_year") or metadata.get("published_year") or metadata.get(
        "published_date"
    )
    source_url = str(metadata.get("url", "") or source_id)
    stype = source_type.lower()

    if stype == "pubmed":
        author_credibility = "known_org"
    elif "mayoclinic" in source_url.lower() or "mayo" in source_url.lower():
        author_credibility = "known_org"
    else:
        author_credibility = "independent"

    citation_count = int(metadata.get("citation_count", 0) or 0)
    if citation_count == 0:
        citation_count = len(content_chunks)

    is_medical_content = stype == "pubmed" or "health" in source_url.lower() or "mayo" in source_url.lower()

    scoring_metadata = {
        "source_type": stype,
        "source": source_url,
        "author_credibility": author_credibility,
        "citation_count": citation_count,
        "published_year": published_year,
        "is_medical_content": is_medical_content,
        "has_medical_disclaimer": medical_disclaimer_presence,
        "medical_disclaimer_presence": medical_disclaimer_presence,
        "text_for_disclaimer_check": content,
    }

    return float(score_from_metadata(scoring_metadata).trust_score)


def _empty_record(source_type: str, source: str) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "source_id": None,
        "source": source,
        "metadata": {},
        "content": "",
        "content_chunks": [],
        "medical_disclaimer_presence": None,
        "has_medical_disclaimer": None,
        "trust_score": 0.0,
        "status": "error",
        "error": None,
    }


def _ensure_record_keys(record: dict[str, Any]) -> dict[str, Any]:
    for key in REQUIRED_RECORD_KEYS:
        if key not in record:
            if key in {"metadata"}:
                record[key] = {}
            elif key in {"content_chunks"}:
                record[key] = []
            elif key in {"trust_score"}:
                record[key] = 0.0
            else:
                record[key] = None

    # Trust score must always be serialized as float.
    record["trust_score"] = float(record.get("trust_score", 0.0) or 0.0)
    record["content_chunks"] = [str(chunk) for chunk in record.get("content_chunks", [])]
    return record


if __name__ == "__main__":
    main()
