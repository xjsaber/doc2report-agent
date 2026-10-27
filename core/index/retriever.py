"""Backend-independent retrieval contract for memory and Milvus Lite."""

from collections.abc import Sequence
from typing import Protocol

from core.models import Chunk, SearchHit, SearchMode


class Retriever(Protocol):
    def index_chunks(self, chunks: Sequence[Chunk]) -> None:
        """Upsert source-preserving chunks by chunk_id; empty input is a no-op."""
        ...

    def search(
        self,
        query: str,
        doc_ids: Sequence[str] | None = None,
        top_k: int = 8,
        mode: SearchMode = "hybrid",
    ) -> list[SearchHit]:
        """Return descending scores, scoped before ranking; [] scope matches nothing.

        Blank queries/empty indexes return []; invalid modes/top_k < 1 raise ValueError.
        Scores are backend/mode-specific, not probabilities.
        """
        ...
