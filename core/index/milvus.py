"""Milvus Lite vectors with shared temporary BM25/hybrid ranking.

Collections are session-scoped: re-index source chunks after opening a retriever.
"""

from collections.abc import Sequence
import json
from pathlib import Path
import sys
from uuid import uuid4

import numpy as np

from core.index.memory import Embedder, MemoryRetriever, hash_embeddings
from core.models import Chunk


class MilvusRetriever(MemoryRetriever):
    def __init__(self, *, embedder: Embedder = hash_embeddings,
                 uri: str = "data/index/milvus.db") -> None:
        if sys.platform == "win32":
            raise RuntimeError("Milvus Lite cannot run on native Windows; set RETRIEVER=memory "
                               "or run this application in Docker/Linux/macOS/WSL.")
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise RuntimeError('Install the milvus extra: pip install -e ".[milvus]"') from exc
        super().__init__(embedder=embedder)
        if "://" not in uri:
            Path(uri).parent.mkdir(parents=True, exist_ok=True)
        self._client = MilvusClient(uri=uri)
        self._collection = f"chunks_{uuid4().hex}"
        self._created = False

    def _store_vectors(self, chunks: Sequence[Chunk], vectors: np.ndarray) -> None:
        if not self._created:
            self._client.create_collection(collection_name=self._collection,
                dimension=vectors.shape[1], id_type="string", max_length=512,
                metric_type="COSINE", consistency_level="Strong")
            self._created = True
        self._client.upsert(collection_name=self._collection, data=[
            {"id": chunk.chunk_id, "vector": vector.tolist()}
            for chunk, vector in zip(chunks, vectors)])

    def _vector_scores(self, query: np.ndarray, chunks: Sequence[Chunk]) -> np.ndarray:
        scores: dict[str, float] = {}
        # Batch candidate IDs to respect search limits and pre-filter by doc_ids.
        for start in range(0, len(chunks), 1000):
            batch = chunks[start:start + 1000]
            results = self._client.search(collection_name=self._collection,
                data=[query.tolist()], filter="id in " + json.dumps([c.chunk_id for c in batch]),
                limit=len(batch), search_params={"metric_type": "COSINE"})
            scores.update((hit["id"], float(hit["distance"])) for hit in results[0])
        return np.asarray([scores.get(chunk.chunk_id, 0.0) for chunk in chunks])

    def close(self) -> None:
        """Release session collection/client; no persistent BM25 catalog yet."""
        try:
            if self._created:
                self._client.drop_collection(collection_name=self._collection)
                self._created = False
        finally:
            self._client.close()
