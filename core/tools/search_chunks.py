"""Search document chunks: contracts only, no business logic."""

from typing import Literal

from pydantic import BaseModel, Field

from core.models import SearchHit, SearchMode, ToolMetadata, ToolResult
from core.index.retriever import Retriever

METADATA = ToolMetadata(name="search_chunks", description_zh="检索文档片段", description_en="Search document chunks")


class SearchChunksInput(BaseModel):
    query: str
    doc_ids: list[str] | None = None
    top_k: int = Field(default=8, ge=1)
    mode: SearchMode = "hybrid"


class SearchChunksData(BaseModel):
    chunks: list[SearchHit]


SearchChunksOutput = ToolResult[SearchChunksData]


def search_chunks(request: SearchChunksInput, *, retriever: Retriever) -> SearchChunksOutput:
    raise NotImplementedError("Step 1: search_chunks contract only")
