"""Search through the Retriever contract and preserve source metadata."""

import logging
from time import perf_counter

from pydantic import BaseModel, Field

from core.models import SearchHit, SearchMode, Source, ToolMetadata, ToolResult
from core.index.retriever import Retriever

METADATA = ToolMetadata(name="search_chunks", description_zh="检索文档片段", description_en="Search document chunks")
logger = logging.getLogger(__name__)


class SearchChunksInput(BaseModel):
    query: str
    doc_ids: list[str] | None = None
    top_k: int = Field(default=8, ge=1)
    mode: SearchMode = "hybrid"


class SearchChunksData(BaseModel):
    chunks: list[SearchHit]


SearchChunksOutput = ToolResult[SearchChunksData]


def search_chunks(request: SearchChunksInput, *, retriever: Retriever) -> SearchChunksOutput:
    started = perf_counter()
    try:
        hits = retriever.search(request.query, doc_ids=request.doc_ids,
                                top_k=request.top_k, mode=request.mode)
        result = SearchChunksOutput(ok=True, data=SearchChunksData(chunks=hits),
            sources=[Source(file=h.file, page=h.page, chunk_id=h.chunk_id) for h in hits])
    except Exception as exc:
        result = SearchChunksOutput(ok=False, error=f"{type(exc).__name__}: {exc}")
    logger.info(
        "tool=search_chunks query_chars=%d doc_count=%s top_k=%d mode=%s elapsed_seconds=%.6f ok=%s",
        len(request.query), None if request.doc_ids is None else len(request.doc_ids),
        request.top_k, request.mode, perf_counter() - started, result.ok,
    )
    return result
