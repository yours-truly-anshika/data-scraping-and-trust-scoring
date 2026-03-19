from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


CURRENT_YEAR = 2026


DOMAIN_AUTHORITY_MAP: dict[str, float] = {
    "ncbi.nlm.nih.gov": 1.0,
    "nih.gov": 0.95,
    "who.int": 0.95,
    "mayoclinic.org": 0.9,
    "youtube.com": 0.6,
    "youtu.be": 0.6,
    "medium.com": 0.5,
    "wordpress.com": 0.4,
    "blogspot.com": 0.3,
}


DEFAULT_WEIGHTS: dict[str, float] = {
    "ac": 0.25,
    "cc": 0.2,
    "da": 0.2,
    "r": 0.2,
    "md": 0.15,
}


DISCLAIMER_HINTS = (
    "medical disclaimer",
    "not medical advice",
    "for informational purposes only",
    "consult your physician",
    "consult a healthcare professional",
)


@dataclass
class TrustScoreInput:
    source_type: str
    source: str
    author_credibility: str
    citation_count: int
    published_year: int | None
    is_medical_content: bool = False
    has_medical_disclaimer: bool | None = None
    text_for_disclaimer_check: str | None = None
    max_citation_scale: int = 1000
    recency_decay: float = 0.35
    weights: dict[str, float] | None = None


@dataclass
class TrustScoreBreakdown:
    ac: float
    cc: float
    da: float
    r: float
    md: float
    weighted_sum: float
    penalty_applied: bool
    pubmed_disclaimer_penalty_applied: bool
    recency_cap_applied: bool
    trust_score: float


def compute_trust_score(payload: TrustScoreInput) -> TrustScoreBreakdown:
    """Compute normalized trust score in [0, 1] using weighted components.

    Trust Score = (w1*AC) + (w2*CC) + (w3*DA) + (w4*R) + (w5*MD)
    """
    weights = _normalize_weights(payload.weights or DEFAULT_WEIGHTS)

    ac = score_author_credibility(payload.author_credibility)
    cc = score_citation_count(payload.citation_count, payload.max_citation_scale)
    da = score_domain_authority(payload.source)
    r = score_recency(payload.published_year, current_year=CURRENT_YEAR, decay=payload.recency_decay)
    md = score_medical_disclaimer(payload)

    weighted_sum = (
        (weights["ac"] * ac)
        + (weights["cc"] * cc)
        + (weights["da"] * da)
        + (weights["r"] * r)
        + (weights["md"] * md)
    )

    source_type = payload.source_type.strip().lower()
    years_old = _years_old(payload.published_year, current_year=CURRENT_YEAR)

    # Abuse-prevention rule 1: hard-coded PubMed disclaimer multiplier.
    pubmed_disclaimer_penalty_applied = source_type == "pubmed" and md < 1.0
    final_score = weighted_sum * 0.5 if pubmed_disclaimer_penalty_applied else weighted_sum

    # Abuse-prevention rule 2: cap stale content to 0.7 when older than 5 years.
    recency_cap_applied = years_old > 5
    if recency_cap_applied:
        final_score = min(final_score, 0.7)

    penalty_applied = pubmed_disclaimer_penalty_applied or recency_cap_applied

    return TrustScoreBreakdown(
        ac=ac,
        cc=cc,
        da=da,
        r=r,
        md=md,
        weighted_sum=_clamp01(weighted_sum),
        penalty_applied=penalty_applied,
        pubmed_disclaimer_penalty_applied=pubmed_disclaimer_penalty_applied,
        recency_cap_applied=recency_cap_applied,
        trust_score=_clamp01(final_score),
    )


def score_author_credibility(author_credibility: str) -> float:
    """AC: 1 for known org/verified, 0.5 for independent, 0 for anonymous."""
    key = author_credibility.strip().lower()
    if key in {"known_org", "known-org", "verified", "organization"}:
        return 1.0
    if key in {"independent", "individual"}:
        return 0.5
    if key in {"anonymous", "unknown", ""}:
        return 0.0
    raise ValueError("author_credibility must be one of: known_org, independent, anonymous")


def score_citation_count(citation_count: int, max_citation_scale: int = 1000) -> float:
    """CC: log-normalized citation count in [0, 1]."""
    if max_citation_scale <= 0:
        raise ValueError("max_citation_scale must be > 0")
    safe_count = max(citation_count, 0)
    numerator = math.log1p(safe_count)
    denominator = math.log1p(max_citation_scale)
    return _clamp01(numerator / denominator)


def score_domain_authority(source: str) -> float:
    """DA: map source domain to authority score using assignment mock mapping."""
    domain = _extract_domain(source)
    if not domain:
        return 0.5

    if domain in DOMAIN_AUTHORITY_MAP:
        return DOMAIN_AUTHORITY_MAP[domain]

    for known_domain, score in DOMAIN_AUTHORITY_MAP.items():
        if domain.endswith(f".{known_domain}"):
            return score

    return 0.5


def score_recency(
    published_year: int | None,
    current_year: int = CURRENT_YEAR,
    decay: float = 0.35,
) -> float:
    """R: exponential decay by age in years from current date (2026 baseline)."""
    if published_year is None:
        return 0.0
    years_old = max(0, current_year - published_year)
    return _clamp01(math.exp(-decay * years_old))


def score_medical_disclaimer(payload: TrustScoreInput) -> float:
    """MD: boolean score for medical disclaimer presence."""
    if payload.has_medical_disclaimer is not None:
        return 1.0 if payload.has_medical_disclaimer else 0.0

    if payload.text_for_disclaimer_check:
        lowered = payload.text_for_disclaimer_check.lower()
        return 1.0 if any(hint in lowered for hint in DISCLAIMER_HINTS) else 0.0

    return 0.0


def is_medical_disclaimer_required(source_type: str, is_medical_content: bool) -> bool:
    """MD requirement: mandatory for PubMed and medical blogs."""
    stype = source_type.strip().lower()
    if stype == "pubmed":
        return True
    if stype == "blog" and is_medical_content:
        return True
    return False


def score_from_metadata(metadata: dict[str, Any]) -> TrustScoreBreakdown:
    """Convenience wrapper to score from normalized metadata dicts."""
    payload = TrustScoreInput(
        source_type=str(metadata.get("source_type", "")),
        source=str(metadata.get("source", metadata.get("url", ""))),
        author_credibility=str(metadata.get("author_credibility", "anonymous")),
        citation_count=int(metadata.get("citation_count", 0) or 0),
        published_year=_safe_int(metadata.get("published_year")),
        is_medical_content=bool(metadata.get("is_medical_content", False)),
        has_medical_disclaimer=(
            bool(metadata.get("has_medical_disclaimer"))
            if metadata.get("has_medical_disclaimer") is not None
            else (
                bool(metadata.get("medical_disclaimer_presence"))
                if metadata.get("medical_disclaimer_presence") is not None
                else None
            )
        ),
        text_for_disclaimer_check=(
            metadata.get("text_for_disclaimer_check")
            if metadata.get("text_for_disclaimer_check") is not None
            else None
        ),
    )
    return compute_trust_score(payload)


def _years_old(published_year: int | None, current_year: int = CURRENT_YEAR) -> int:
    if published_year is None:
        return current_year
    return max(0, current_year - published_year)


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    required_keys = {"ac", "cc", "da", "r", "md"}
    missing = required_keys - set(weights)
    if missing:
        raise ValueError(f"Missing weight keys: {sorted(missing)}")

    total = sum(max(value, 0.0) for value in weights.values())
    if total <= 0:
        raise ValueError("At least one weight must be > 0")

    return {key: max(value, 0.0) / total for key, value in weights.items()}


def _extract_domain(source: str) -> str:
    text = source.strip().lower()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    domain = parsed.netloc or parsed.path
    return domain.split(":", 1)[0].lstrip("www.")


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if len(stripped) >= 4 and stripped[:4].isdigit():
            return int(stripped[:4])
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
