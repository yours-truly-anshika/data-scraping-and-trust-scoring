from __future__ import annotations

import math
import re
from collections import Counter


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_ENTITY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")

_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "among",
    "been",
    "being",
    "between",
    "could",
    "does",
    "each",
    "from",
    "have",
    "into",
    "just",
    "like",
    "many",
    "more",
    "most",
    "other",
    "over",
    "such",
    "than",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
}

_STOPWORDS.update(
    {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "was",
        "are",
        "but",
        "not",
        "can",
        "out",
        "all",
        "get",
        "has",
        "had",
        "his",
        "her",
        "him",
        "one",
        "two",
        "use",
        "how",
        "you",
        "our",
        "its",
    }
)


def extract_topic_tags(text_or_chunks: str | list[str], top_k: int = 5) -> list[str]:
    """Extract top topic tags using TF-IDF, with named-entity-like phrase support.

    If a single string is provided, paragraphs are treated as separate documents
    for IDF estimation. If no paragraph split is available, one document is used.
    """
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    documents = _normalize_documents(text_or_chunks)
    if not documents:
        return []

    tokenized_docs = [_tokenize(doc) for doc in documents]
    entity_docs = [_extract_entity_phrases(doc) for doc in documents]

    tfidf_scores = _compute_tfidf(tokenized_docs)
    entity_scores = _compute_tfidf(entity_docs)

    # Give slight preference to named-entity-like phrases where present.
    combined = Counter(tfidf_scores)
    for phrase, score in entity_scores.items():
        combined[phrase] += score * 1.25

    ranked = [term for term, _score in combined.most_common(top_k)]
    return ranked


def _normalize_documents(text_or_chunks: str | list[str]) -> list[str]:
    if isinstance(text_or_chunks, str):
        text = text_or_chunks.strip()
        if not text:
            return []
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
        return paragraphs if paragraphs else [text]

    return [chunk.strip() for chunk in text_or_chunks if chunk and chunk.strip()]


def _tokenize(text: str) -> list[str]:
    tokens = [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]
    return [token for token in tokens if token not in _STOPWORDS]


def _extract_entity_phrases(text: str) -> list[str]:
    phrases = [m.group(1).strip() for m in _ENTITY_RE.finditer(text)]
    normalized: list[str] = []
    for phrase in phrases:
        if len(phrase) < 4:
            continue
        lower = phrase.lower()
        if lower in _STOPWORDS:
            continue
        normalized.append(lower)
    return normalized


def _compute_tfidf(tokenized_docs: list[list[str]]) -> Counter[str]:
    doc_count = len(tokenized_docs)
    if doc_count == 0:
        return Counter()

    doc_freq: Counter[str] = Counter()
    term_freqs: list[Counter[str]] = []

    for tokens in tokenized_docs:
        tf = Counter(tokens)
        term_freqs.append(tf)
        doc_freq.update(set(tokens))

    scores: Counter[str] = Counter()
    for tf in term_freqs:
        max_tf = max(tf.values(), default=1)
        for term, count in tf.items():
            normalized_tf = count / max_tf
            idf = math.log((1 + doc_count) / (1 + doc_freq[term])) + 1
            scores[term] += normalized_tf * idf

    return scores
