"""Small in-memory retrieval scaffold. No model downloads or network calls."""

from collections.abc import Callable, Sequence
from hashlib import sha256
import re

import numpy as np
from rank_bm25 import BM25Okapi

from core.models import Chunk, SearchHit, SearchMode

Embedder = Callable[[Sequence[str]], np.ndarray]


def tokenize(text: str) -> list[str]:
    """Temporary Latin words / individual Han characters; jieba comes later."""
    return re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", text.lower())


def hash_embeddings(texts: Sequence[str]) -> np.ndarray:
    """Deterministic test/demo placeholder, NOT semantic embeddings."""
    vectors = np.zeros((len(texts), 64), dtype=np.float32)
    for row, text in enumerate(texts):
        for token in tokenize(text):
            vectors[row, int.from_bytes(sha256(token.encode()).digest()[:4], "big") % 64] += 1
    return vectors


class MemoryRetriever:
    def __init__(self, *, embedder: Embedder = hash_embeddings) -> None:
        self.embedder = embedder
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, np.ndarray] = {}
        self._dimension: int | None = None

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        vectors = np.asarray(self.embedder(texts), dtype=np.float32)
        if (vectors.ndim != 2 or vectors.shape[0] != len(texts) or vectors.shape[1] < 2
                or not np.isfinite(vectors).all()):
            raise ValueError("Embedding must be a finite (text_count, dimension >= 2) matrix")
        if self._dimension is not None and vectors.shape[1] != self._dimension:
            raise ValueError("Embedding dimension changed")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)

    def _store_vectors(self, chunks: Sequence[Chunk], vectors: np.ndarray) -> None:
        pass

    def index_chunks(self, chunks: Sequence[Chunk]) -> None:
        """Upsert by chunk_id. Empty input is a no-op; caller mutations are isolated."""
        if not chunks:
            return
        chunks = list({chunk.chunk_id: chunk.model_copy(deep=True) for chunk in chunks}.values())
        vectors = self._embed([chunk.text for chunk in chunks])
        self._store_vectors(chunks, vectors)
        self._dimension = vectors.shape[1]
        self._chunks.update((chunk.chunk_id, chunk) for chunk in chunks)
        self._vectors.update((chunk.chunk_id, vector) for chunk, vector in zip(chunks, vectors))

    def _vector_scores(self, query: np.ndarray, chunks: Sequence[Chunk]) -> np.ndarray:
        return np.asarray([self._vectors[chunk.chunk_id] @ query for chunk in chunks])

    def search(self, query: str, doc_ids: Sequence[str] | None = None,
               top_k: int = 8, mode: SearchMode = "hybrid") -> list[SearchHit]:
        if mode not in ("hybrid", "vector", "bm25"):
            raise ValueError(f"Unsupported search mode: {mode}")
        if top_k < 1:
            raise ValueError("top_k must be positive")
        allowed = None if doc_ids is None else set(doc_ids)
        chunks = [chunk for chunk in self._chunks.values() if allowed is None or chunk.doc_id in allowed]
        if not chunks or not query.strip():
            return []
        vector = self._vector_scores(self._embed([query])[0], chunks) if mode != "bm25" else None
        bm25 = None
        if mode != "vector":
            corpus = [tokenize(chunk.text) for chunk in chunks]
            bm25 = (BM25Okapi(corpus).get_scores(tokenize(query)) if any(corpus)
                    else np.zeros(len(chunks)))
        if mode == "vector":
            scores = vector
        elif mode == "bm25":
            scores = bm25
        else:
            # Temporary score sum only. RRF and production ranking belong to task 2.
            scores = vector + bm25 / max(1.0, float(np.max(np.abs(bm25))))
        order = sorted(range(len(chunks)), key=lambda i: (-float(scores[i]), chunks[i].chunk_id))[:top_k]
        return [SearchHit(**chunks[i].model_dump(), score=float(scores[i])) for i in order]
