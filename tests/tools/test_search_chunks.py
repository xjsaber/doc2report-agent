import pytest

from core.index import get_retriever
from core.models import Chunk
from core.tools.search_chunks import SearchChunksInput, search_chunks


@pytest.mark.parametrize("mode", ["hybrid", "vector", "bm25"])
def test_search_success(mode, caplog):
    retriever = get_retriever()
    chunks = [Chunk(chunk_id=str(i), doc_id="公开合成", file="synthetic.pdf", page=i,
                    section="财务表现", text=text) for i, text in enumerate(
        ["营业收入同比增长", "研发投入稳步增加", "资产负债结构", "公司治理情况"], 1)]
    retriever.index_chunks(chunks)
    with caplog.at_level("INFO"):
        result = search_chunks(SearchChunksInput(query="营业收入", mode=mode,
                               doc_ids=["公开合成"], top_k=1), retriever=retriever)
    assert result.ok and result.error is None
    assert len(result.data.chunks) == 1
    hit = result.data.chunks[0]
    assert hit.model_dump(exclude={"score"}) == chunks[0].model_dump()
    assert result.sources[0].model_dump() == {"file": hit.file, "page": hit.page, "chunk_id": hit.chunk_id}
    assert all(s in caplog.text for s in ["tool=search_chunks", "query_chars=4", "doc_count=1",
                                        "top_k=1", f"mode={mode}", "elapsed_seconds=", "ok=True"])


def test_search_error(caplog):
    class BrokenRetriever:
        def search(self, query, **kwargs):
            raise RuntimeError("synthetic backend failure")

    with caplog.at_level("INFO"):
        result = search_chunks(SearchChunksInput(query="营业收入"), retriever=BrokenRetriever())
    assert not result.ok and result.data is None and result.sources == []
    assert result.error == "RuntimeError: synthetic backend failure"
    assert "ok=False" in caplog.text and "elapsed_seconds=" in caplog.text


def test_search_empty():
    result = search_chunks(SearchChunksInput(query="营业收入"), retriever=get_retriever())
    assert result.ok and result.data.chunks == [] and result.sources == []
