"""Injectable batch embeddings; optional local models load on first use."""

from collections.abc import Sequence
from hashlib import sha256
import os
from typing import Protocol

import jieba
import numpy as np


def tokenize(text: str) -> list[str]:
    return [token for token in jieba.lcut(text.lower()) if any(c.isalnum() for c in token)]


class EmbeddingProvider(Protocol):
    def __call__(self, texts: Sequence[str]) -> np.ndarray:
        """Return a finite matrix with one row per text, at least two columns."""
        ...


def hash_embeddings(texts: Sequence[str]) -> np.ndarray:
    """Deterministic fake vectors for tests only; no semantic quality claim."""
    vectors = np.zeros((len(texts), 64), dtype=np.float32)
    for row, text in enumerate(texts):
        for token in tokenize(text):
            vectors[row, int.from_bytes(sha256(token.encode()).digest()[:4], "big") % 64] += 1
    return vectors


class LocalEmbeddingProvider:
    def __init__(self, model: str | None = None, device: str | None = None) -> None:
        self.model_name = model or os.getenv("EMBEDDING_MODEL") or "BAAI/bge-small-zh-v1.5"
        self.device = device or os.getenv("EMBED_DEVICE") or None
        self._model = None

    def __call__(self, texts: Sequence[str]) -> np.ndarray:
        if self._model is None:
            try:
                import torch
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError('Install local embeddings: pip install -e ".[embedding]"; '
                                   'use EMBEDDING_BACKEND=fake only for tests') from exc
            self.device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
            # Prefer cache; if missing, allow a one-time network fetch (model files stay local, never committed).
            try:
                self._model = SentenceTransformer(
                    self.model_name, device=self.device, local_files_only=True
                )
            except Exception:
                self._model = SentenceTransformer(self.model_name, device=self.device)
        return np.asarray(self._model.encode(list(texts), convert_to_numpy=True,
                                            normalize_embeddings=True, show_progress_bar=False))


def get_embedding_provider() -> EmbeddingProvider:
    backend = os.getenv("EMBEDDING_BACKEND", "local")
    if backend == "fake":
        return hash_embeddings
    if backend == "local":
        return LocalEmbeddingProvider()
    raise ValueError(f"Unsupported EMBEDDING_BACKEND: {backend}; choose fake or local")
