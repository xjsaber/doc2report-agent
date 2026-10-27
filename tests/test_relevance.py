"""Relevance gate and query-instruction helpers."""

import numpy as np

from core.index.query_instruction import (
    DEFAULT_EMBED_QUERY_INSTRUCTION,
    apply_query_instruction,
    resolve_query_instruction,
)
from core.index.relevance import filter_relevant_hits
from core.models import SearchHit


def _hit(text: str, chunk_id: str = "1") -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        doc_id="a",
        file="synthetic.pdf",
        text=text,
        page=1,
        page_end=1,
        score=0.5,
    )


def test_query_instruction_default_for_local(monkeypatch):
    monkeypatch.delenv("EMBED_QUERY_INSTRUCTION", raising=False)
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    assert resolve_query_instruction() == DEFAULT_EMBED_QUERY_INSTRUCTION
    assert apply_query_instruction("营收").startswith(DEFAULT_EMBED_QUERY_INSTRUCTION)


def test_query_instruction_empty_disables(monkeypatch):
    monkeypatch.setenv("EMBED_QUERY_INSTRUCTION", "")
    assert resolve_query_instruction() == ""
    assert apply_query_instruction("营收") == "营收"


def test_filter_keeps_bm25_overlap_even_with_low_vector():
    def embed(texts):
        # Query vector is axis-0; document vectors are axis-1 → cosine 0, BM25 must save the hit.
        return np.asarray(
            [[1.0, 0.0] if text.strip() == "营业收入" else [0.0, 1.0] for text in texts],
            dtype=np.float32,
        )

    hits = [_hit("公司营业收入同比增长", "1"), _hit("无关气象记录", "2")]
    kept = filter_relevant_hits("营业收入", hits, embedder=embed, min_vector_score=0.99)
    assert [h.chunk_id for h in kept] == ["1"]


def test_filter_drops_when_both_gates_fail():
    def embed(texts):
        rows = []
        for text in texts:
            rows.append([1.0, 0.0] if "查询轴" in text else [0.0, 1.0])
        return np.asarray(rows, dtype=np.float32)

    hits = [_hit("完全不搭界的文本内容")]
    kept = filter_relevant_hits("查询轴天体物理", hits, embedder=embed, min_vector_score=0.35)
    assert kept == []
