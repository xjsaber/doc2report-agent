"""Relevance gate for retrieved chunks (empirical threshold; pending real-report tuning)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
import os

import numpy as np

from core.index.embeddings import EmbeddingProvider, get_embedding_provider, tokenize
from core.index.query_instruction import apply_query_instruction
from core.models import SearchHit

# Empirical placeholder; not measured on real annual reports yet.
DEFAULT_MIN_VECTOR_SCORE = 0.35

# Small Chinese stopword set for annual-report style text. Words with
# document frequency >50% in the candidate corpus are also treated as stopwords.
_BASE_STOPWORDS = frozenset(
    {
        "的",
        "了",
        "和",
        "与",
        "及",
        "或",
        "在",
        "是",
        "为",
        "等",
        "对",
        "中",
        "上",
        "下",
        "之",
        "其",
        "本",
        "该",
        "以及",
        "关于",
        "我们",
        "进行",
        "通过",
        "根据",
        "相关",
        "情况",
        "内容",
        "方面",
        "公司",
        "有限",
        "股份",
        "集团",
        "年度",
        "报告",
        "年报",
        "本公司",
        "报告期",
        "本期",
        "披露",
        "以下",
        "以上",
        "可以",
        "应当",
        "如果",
        "已经",
        "表示",
        "包括",
        "主要",
        "其他",
        "各项",
        "有关",
        "今年",
        "去年",
        "分别",
        "同时",
        "其中",
    }
)


def resolve_min_vector_score(override: float | None = None) -> float:
    if override is not None:
        return float(override)
    raw = os.getenv("MIN_VECTOR_SCORE")
    if raw is None or not str(raw).strip():
        return DEFAULT_MIN_VECTOR_SCORE
    return float(raw)


def build_stopwords(corpus_texts: Sequence[str]) -> set[str]:
    """Union of the base list and tokens whose document frequency exceeds 50%."""
    stops = set(_BASE_STOPWORDS)
    docs = [t for t in corpus_texts if (t or "").strip()]
    if len(docs) < 2:
        return stops
    df: Counter[str] = Counter()
    for text in docs:
        for token in set(tokenize(text)):
            df[token] += 1
    threshold = len(docs) * 0.5
    for token, count in df.items():
        if count > threshold:
            stops.add(token)
    return stops


def meaningful_tokens(text: str, stopwords: set[str]) -> set[str]:
    return {token for token in tokenize(text) if token not in stopwords}


def has_bm25_overlap(
    query: str,
    text: str,
    *,
    stopwords: set[str] | None = None,
) -> bool:
    """True when non-stopword jieba tokens overlap between query and text."""
    stops = stopwords if stopwords is not None else set(_BASE_STOPWORDS)
    query_tokens = meaningful_tokens(query, stops)
    if not query_tokens:
        return False
    return bool(query_tokens & meaningful_tokens(text, stops))


def _cosine_against_query(
    query_vec: np.ndarray,
    doc_vecs: np.ndarray,
) -> np.ndarray:
    q = np.asarray(query_vec, dtype=np.float64).reshape(-1)
    docs = np.asarray(doc_vecs, dtype=np.float64)
    if docs.ndim == 1:
        docs = docs.reshape(1, -1)
    q_norm = float(np.linalg.norm(q))
    if q_norm == 0 or docs.size == 0:
        return np.zeros(docs.shape[0], dtype=np.float64)
    doc_norms = np.linalg.norm(docs, axis=1)
    doc_norms = np.where(doc_norms == 0, 1.0, doc_norms)
    return (docs @ q) / (doc_norms * q_norm)


def filter_relevant_hits(
    query: str,
    hits: Sequence[SearchHit],
    *,
    embedder: EmbeddingProvider | None = None,
    min_vector_score: float | None = None,
    hit_vectors: Sequence[np.ndarray | None] | None = None,
) -> list[SearchHit]:
    """Drop hits with no BM25 token overlap AND cosine < MIN_VECTOR_SCORE (default 0.35,待实测).

    Prefer reusing ``hit_vectors`` already stored by the Retriever so local BGE
    does not re-encode every retrieved passage.
    """
    if not hits:
        return []
    query = (query or "").strip()
    if not query:
        return []

    threshold = resolve_min_vector_score(min_vector_score)
    stopwords = build_stopwords([hit.text for hit in hits])

    provider = embedder if embedder is not None else get_embedding_provider()
    query_vec = np.asarray(provider([apply_query_instruction(query)]), dtype=np.float32)
    if query_vec.ndim != 2 or query_vec.shape[0] != 1:
        raise ValueError("Embedding must return a single query row")

    reuse: list[np.ndarray | None]
    if hit_vectors is None:
        reuse = [None] * len(hits)
    else:
        if len(hit_vectors) != len(hits):
            raise ValueError("hit_vectors length must match hits")
        reuse = list(hit_vectors)

    missing_indices = [i for i, vec in enumerate(reuse) if vec is None]
    if missing_indices:
        recomputed = np.asarray(
            provider([hits[i].text for i in missing_indices]),
            dtype=np.float32,
        )
        if recomputed.ndim != 2 or recomputed.shape[0] != len(missing_indices):
            raise ValueError("Embedding must return 2-D matrices")
        for row, index in enumerate(missing_indices):
            reuse[index] = recomputed[row]

    doc_matrix = np.asarray([np.asarray(v, dtype=np.float32) for v in reuse], dtype=np.float32)
    cosines = _cosine_against_query(query_vec[0], doc_matrix)

    kept: list[SearchHit] = []
    for index, hit in enumerate(hits):
        if has_bm25_overlap(query, hit.text, stopwords=stopwords) or float(cosines[index]) >= threshold:
            kept.append(hit)
    return kept
