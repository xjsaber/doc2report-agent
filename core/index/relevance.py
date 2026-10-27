"""Relevance gate for retrieved chunks (empirical threshold; pending real-report tuning)."""

from __future__ import annotations

from collections.abc import Sequence
import os

import numpy as np

from core.index.embeddings import EmbeddingProvider, get_embedding_provider, tokenize
from core.index.query_instruction import apply_query_instruction
from core.models import SearchHit

# Empirical placeholder; not measured on real annual reports yet.
DEFAULT_MIN_VECTOR_SCORE = 0.35


def resolve_min_vector_score(override: float | None = None) -> float:
    if override is not None:
        return float(override)
    raw = os.getenv("MIN_VECTOR_SCORE")
    if raw is None or not str(raw).strip():
        return DEFAULT_MIN_VECTOR_SCORE
    return float(raw)


def has_bm25_overlap(query: str, text: str) -> bool:
    """True when jieba tokens overlap. rank_bm25 may yield <=0 even with overlap on tiny corpora."""
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return False
    return bool(query_tokens & set(tokenize(text)))


def filter_relevant_hits(
    query: str,
    hits: Sequence[SearchHit],
    *,
    embedder: EmbeddingProvider | None = None,
    min_vector_score: float | None = None,
) -> list[SearchHit]:
    """Drop hits with no BM25 token overlap AND cosine < MIN_VECTOR_SCORE (default 0.35,待实测)."""
    if not hits:
        return []
    query = (query or "").strip()
    if not query:
        return []

    threshold = resolve_min_vector_score(min_vector_score)
    provider = embedder if embedder is not None else get_embedding_provider()
    query_vec = np.asarray(provider([apply_query_instruction(query)]), dtype=np.float32)
    doc_vecs = np.asarray(provider([hit.text for hit in hits]), dtype=np.float32)
    if query_vec.ndim != 2 or doc_vecs.ndim != 2:
        raise ValueError("Embedding must return 2-D matrices")
    q = query_vec[0]
    q_norm = float(np.linalg.norm(q))
    if q_norm == 0:
        cosines = np.zeros(len(hits), dtype=np.float64)
    else:
        doc_norms = np.linalg.norm(doc_vecs, axis=1)
        doc_norms = np.where(doc_norms == 0, 1.0, doc_norms)
        cosines = (doc_vecs @ q) / (doc_norms * q_norm)

    kept: list[SearchHit] = []
    for index, hit in enumerate(hits):
        if has_bm25_overlap(query, hit.text) or float(cosines[index]) >= threshold:
            kept.append(hit)
    return kept
