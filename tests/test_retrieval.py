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


def test_factory(monkeypatch):
    assert isinstance(get_retriever(), MemoryRetriever)
    monkeypatch.delenv("RETRIEVER")
    monkeypatch.setattr(sys, "platform", "win32")
    assert isinstance(get_retriever(), MemoryRetriever)
    with pytest.raises(RuntimeError, match="RETRIEVER=memory.*Docker"):
        get_retriever("milvus")
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
