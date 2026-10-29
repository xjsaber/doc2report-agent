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


def test_filter_keeps_bm25_overlap_even_with_low_vector(monkeypatch):
    # Disable BGE query-instruction prefix so the stub can recognize the bare query.
    monkeypatch.setenv("EMBED_QUERY_INSTRUCTION", "")

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

def test_stopwords_block_boilerplate_overlap():
    from core.index.relevance import has_bm25_overlap, build_stopwords

    corpus = [
        "本公司年度报告披露公司基本情况与治理结构。",
        "本公司年度报告说明公司董事会运作情况。",
        "本公司年度报告列示公司股东大会决议。",
    ]
    stops = build_stopwords(corpus)
    assert "公司" in stops
    assert "年度" in stops or "报告" in stops
    # Query only shares boilerplate stopwords with a hit → no meaningful overlap.
    assert has_bm25_overlap("公司年度报告里火星移民计划进展", corpus[0], stopwords=stops) is False


def test_filter_reuses_hit_vectors_without_reembedding_docs():
    calls = {"n": 0}

    def embed(texts):
        calls["n"] += 1
        # Only the query should be embedded when hit_vectors are supplied.
        assert len(texts) == 1
        return np.asarray([[1.0, 0.0]], dtype=np.float32)

    hits = [_hit("完全不搭界的文本内容", "1"), _hit("另一段无关文字", "2")]
    stored = [np.asarray([0.0, 1.0], dtype=np.float32), np.asarray([0.0, 1.0], dtype=np.float32)]
    kept = filter_relevant_hits(
        "查询轴专用短语",
        hits,
        embedder=embed,
        min_vector_score=0.99,
        hit_vectors=stored,
    )
    assert kept == []
    assert calls["n"] == 1

