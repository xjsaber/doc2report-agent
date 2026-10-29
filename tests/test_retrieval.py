import sys

import numpy as np
import pytest

from core.index import get_retriever
from core.index.memory import MemoryRetriever
from core.models import Chunk


def fake_embedding(texts):
    return np.asarray([[text.lower().count("apple"), text.lower().count("pear"), 1]
                       for text in texts], dtype=np.float32)


@pytest.fixture(params=["memory", "milvus"])
def retriever(request, tmp_path):
    if request.param == "milvus":
        if sys.platform == "win32":
            pytest.skip("Milvus Lite unavailable on native Windows; run contracts in Linux/macOS/WSL")
        pytest.importorskip("pymilvus", reason="Install milvus extra to run real Milvus contracts")
        pytest.importorskip("milvus_lite", reason="Install milvus extra to run real Milvus contracts")
    instance = get_retriever(request.param, embedder=fake_embedding, uri=str(tmp_path / "index.db"))
    yield instance
    if hasattr(instance, "close"):
        instance.close()


def chunk(i, text, doc="a"):
    return Chunk(chunk_id=str(i), doc_id=doc, text=text, file="synthetic.pdf", page=i,
                 page_end=i + 1, section="Synthetic section")


@pytest.mark.parametrize("mode", ["hybrid", "vector", "bm25"])
def test_index_search_contract(retriever, mode):
    assert retriever.search("apple", mode=mode) == []
    chunks = [chunk(1, "apple apple"), chunk(2, "pear", "b"), chunk(3, "plum"), chunk(4, "orange")]
    retriever.index_chunks(chunks)
    retriever.index_chunks(chunks)
    retriever.index_chunks([])
    hits = retriever.search("apple", top_k=10, mode=mode)
    assert len(hits) == 4
    assert hits[0].chunk_id == "1"
    assert hits[0].model_dump(exclude={"score"}) == chunks[0].model_dump()
    assert all(np.isfinite(hit.score) for hit in hits)
    assert [hit.score for hit in hits] == sorted([hit.score for hit in hits], reverse=True)
    assert len(retriever.search("apple", top_k=1, mode=mode)) == 1
    assert [h.doc_id for h in retriever.search("apple", doc_ids=["b"], mode=mode)] == ["b"]
    assert retriever.search("apple", doc_ids=[], mode=mode) == []
    assert retriever.search("apple", doc_ids=["missing"], mode=mode) == []
    assert retriever.search("  ", mode=mode) == []
    chunks[0].text = "caller mutation"
    assert retriever.search("apple", mode=mode)[0].text == "apple apple"
    retriever.index_chunks([chunk(1, "updated", "b")])
    assert len(retriever.search("apple", mode=mode)) == 4
    assert {h.chunk_id for h in retriever.search("apple", doc_ids=["a"], mode=mode)} == {"3", "4"}


def test_invalid_parameters(retriever):
    with pytest.raises(ValueError, match="mode"):
        retriever.search("a", mode="invalid")
    with pytest.raises(ValueError, match="top_k"):
        retriever.search("a", top_k=0)


@pytest.mark.parametrize("mode", ["hybrid", "vector", "bm25"])
def test_empty_tokens(retriever, mode):
    retriever.index_chunks([chunk(1, "!!!")])
    assert np.isfinite(retriever.search("???", mode=mode)[0].score)


def test_factory(monkeypatch, caplog):
    assert isinstance(get_retriever(), MemoryRetriever)
    monkeypatch.delenv("RETRIEVER", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    assert isinstance(get_retriever(), MemoryRetriever)
    # Explicit milvus on win32 falls back to memory with a warning (no hard crash).
    with caplog.at_level("WARNING"):
        fallback = get_retriever("milvus")
    assert isinstance(fallback, MemoryRetriever)
    assert any("falling back to memory" in r.message for r in caplog.records)
    monkeypatch.setenv("RETRIEVER", "invalid")
    with pytest.raises(ValueError, match="RETRIEVER"):
        get_retriever()
    assert isinstance(get_retriever("memory"), MemoryRetriever)


def test_embedding_validation():
    instance = MemoryRetriever(embedder=lambda texts: np.array([[np.nan, 0]]))
    with pytest.raises(ValueError, match="finite"):
        instance.index_chunks([chunk(1, "apple")])
    assert instance.search("apple") == []
    instance = MemoryRetriever(embedder=lambda texts: np.zeros((len(texts), 2)))
    instance.index_chunks([chunk(1, "apple")])
    assert instance.search("apple", mode="vector")[0].score == 0
    instance.embedder = fake_embedding
    with pytest.raises(ValueError, match="dimension"):
        instance.search("apple")


@pytest.mark.parametrize("mode", ["hybrid", "vector", "bm25"])
def test_chinese_retrieval(retriever, mode):
    from core.index.embeddings import hash_embeddings, tokenize

    assert "收入" in tokenize("营业收入同比增长")
    retriever.embedder = hash_embeddings
    retriever.index_chunks([chunk(1, "营业收入同比增长"), chunk(2, "研发投入增加", "b"),
                            chunk(3, "资产负债结构"), chunk(4, "公司治理情况")])
    assert retriever.search("营业收入", mode=mode, top_k=1)[0].chunk_id == "1"
    assert {h.doc_id for h in retriever.search("营业收入", doc_ids=["b"], mode=mode)} == {"b"}


def test_rrf_exact_ranks(retriever):
    # Lexical winner differs from vector winner; RRF uses ranks, not score magnitude.
    retriever.index_chunks([chunk(1, "apple apple"), chunk(2, "pear"),
                            chunk(3, "plum"), chunk(4, "orange")])
    retriever.embedder = lambda texts: np.asarray([[0, 1, 1] for _ in texts])
    vector = retriever.search("apple", mode="vector")
    lexical = retriever.search("apple", mode="bm25")
    assert vector[0].chunk_id != lexical[0].chunk_id
    expected = {}
    for hits in (vector, lexical):
        for rank, hit in enumerate(hits, 1):
            expected[hit.chunk_id] = expected.get(hit.chunk_id, 0) + 1 / (60 + rank)
    hybrid = retriever.search("apple", mode="hybrid")
    assert {h.chunk_id: h.score for h in hybrid} == pytest.approx(expected)
    assert retriever.search("apple", top_k=1)[0] == hybrid[0]
