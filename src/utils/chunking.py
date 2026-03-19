from __future__ import annotations

import re


def chunk_text(text: str, max_chars: int = 800) -> list[str]:
    """Split text by paragraphs and enforce per-chunk max character size.

    Strategy:
    1) Prefer paragraph boundaries (blank lines).
    2) If a paragraph is too long, split by sentence boundaries.
    3) If a sentence is still too long, split by words.
    """
    if max_chars < 500 or max_chars > 1000:
        raise ValueError("max_chars must be between 500 and 1000")

    cleaned = text.strip()
    if not cleaned:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", cleaned) if p.strip()]
    chunks: list[str] = []

    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue

        sentence_parts = _split_long_paragraph(paragraph, max_chars=max_chars)
        chunks.extend(sentence_parts)

    return chunks


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    # Split around sentence-ending punctuation while preserving punctuation.
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraph) if s.strip()]
    if not sentences:
        return _split_by_words(paragraph, max_chars=max_chars)

    result: list[str] = []
    buffer = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            if buffer:
                result.append(buffer)
                buffer = ""
            result.extend(_split_by_words(sentence, max_chars=max_chars))
            continue

        candidate = sentence if not buffer else f"{buffer} {sentence}"
        if len(candidate) <= max_chars:
            buffer = candidate
        else:
            result.append(buffer)
            buffer = sentence

    if buffer:
        result.append(buffer)

    return result


def _split_by_words(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    pieces: list[str] = []
    buffer = ""

    for word in words:
        # Handle a single token longer than max_chars by hard splitting.
        if len(word) > max_chars:
            if buffer:
                pieces.append(buffer)
                buffer = ""

            start = 0
            while start < len(word):
                end = start + max_chars
                pieces.append(word[start:end])
                start = end
            continue

        if not buffer:
            buffer = word
            continue

        candidate = f"{buffer} {word}"
        if len(candidate) <= max_chars:
            buffer = candidate
        else:
            pieces.append(buffer)
            buffer = word

    if buffer:
        pieces.append(buffer)

    return pieces
