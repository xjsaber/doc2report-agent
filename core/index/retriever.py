"""Backend-independent retrieval contract; Milvus Lite + BM25 is planned."""

from collections.abc import Sequence
from typing import Protocol

from core.models import Chunk, SearchHit, SearchMode


class Retriever(Protocol):
    def index_chunks(self, chunks: Sequence[Chunk]) -> None:
        """Index source-preserving chunks."""
        ...

    def search(
        self,
        query: str,
        doc_ids: Sequence[str] | None = None,
        top_k: int = 8,
        mode: SearchMode = "hybrid",
    ) -> list[SearchHit]:
        """Retrieve ranked chunks, optionally scoped to documents."""
        ...
