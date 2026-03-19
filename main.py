from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scoring import score_from_metadata
from src.utils import extract_topic_tags


INPUT_PATH = PROJECT_ROOT / "data" / "raw" / "acquisition_results.json"
OUTPUT_PATH = PROJECT_ROOT / "output" / "scraped_data.json"


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_PATH}")

    payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))

    payload["blogs"] = [_score_record(record) for record in payload.get("blogs", [])]
    payload["youtube"] = [_score_record(record) for record in payload.get("youtube", [])]

    pubmed = payload.get("pubmed")
    if isinstance(pubmed, dict):
        payload["pubmed"] = _score_record(pubmed)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    print(f"Wrote scored output to: {OUTPUT_PATH}")


def _score_record(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    scoring_metadata = dict(metadata)
    scoring_metadata["source_type"] = record.get("source_type", "")
    scoring_metadata["source"] = record.get("source") or record.get("source_id") or metadata.get("url", "")
    scoring_metadata["medical_disclaimer_presence"] = record.get("medical_disclaimer_presence")
    scoring_metadata["has_medical_disclaimer"] = record.get("has_medical_disclaimer")
    scoring_metadata["text_for_disclaimer_check"] = record.get("content", "")

    try:
        breakdown = score_from_metadata(scoring_metadata)
        record["trust_score"] = float(breakdown.trust_score)
    except Exception:
        # Keep pipeline robust for malformed rows.
        record["trust_score"] = float(record.get("trust_score", 0.0) or 0.0)

    try:
        chunks = record.get("content_chunks")
        if isinstance(chunks, list) and chunks:
            record["topic_tags"] = extract_topic_tags(chunks, top_k=5)
        else:
            record["topic_tags"] = extract_topic_tags(str(record.get("content", "") or ""), top_k=5)
    except Exception:
        record["topic_tags"] = []

    return record


if __name__ == "__main__":
    main()
