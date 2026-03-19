from __future__ import annotations

from typing import Any


DISCLAIMER_PATTERNS = (
    "this is not medical advice",
    "not medical advice",
    "consult a doctor",
    "consult your doctor",
    "consult a healthcare professional",
    "consult your physician",
    "disclaimer",
)


def has_medical_disclaimer(content_chunks: list[dict[str, Any]] | list[str]) -> bool:
    """Return True if disclaimer-like phrases appear in any content chunk."""
    if not content_chunks:
        return False

    texts: list[str] = []
    for chunk in content_chunks:
        if isinstance(chunk, dict):
            texts.append(str(chunk.get("text", "")))
        else:
            texts.append(str(chunk))

    haystack = "\n".join(texts).lower()
    return any(pattern in haystack for pattern in DISCLAIMER_PATTERNS)
