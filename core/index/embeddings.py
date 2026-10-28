"""Injectable batch embeddings; optional local models load on first use."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import argparse
import os
import sys
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


def _allow_download_flag() -> bool:
    raw = (os.getenv("EMBEDDING_ALLOW_DOWNLOAD") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def download_embedding_model(model_name: str | None = None, device: str | None = None) -> str:
    """Explicitly download a local embedding model into the HuggingFace cache.

    Runtime paths must not call this implicitly. Prefer CLI:
    ``python -m core.index.embeddings --download-model``.
    """
    name = model_name or os.getenv("EMBEDDING_MODEL") or "BAAI/bge-small-zh-v1.5"
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            'Install local embeddings first: pip install -e ".[embedding]"'
        ) from exc
    resolved_device = device or os.getenv("EMBED_DEVICE") or (
        "cuda" if torch.cuda.is_available() else "cpu"
    )
    print(f"Downloading embedding model {name!r} to local cache (device={resolved_device})…")
    SentenceTransformer(name, device=resolved_device, local_files_only=False)
    print("Download finished. Subsequent runs use the cache with local_files_only=True.")
    return name


class LocalEmbeddingProvider:
    def __init__(
        self,
        model: str | None = None,
        device: str | None = None,
        *,
        allow_download: bool | None = None,
    ) -> None:
        self.model_name = model or os.getenv("EMBEDDING_MODEL") or "BAAI/bge-small-zh-v1.5"
        self.device = device or os.getenv("EMBED_DEVICE") or None
        self.allow_download = _allow_download_flag() if allow_download is None else bool(allow_download)
        self._model = None

    def __call__(self, texts: Sequence[str]) -> np.ndarray:
        if self._model is None:
            try:
                import torch
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    'Install local embeddings: pip install -e ".[embedding]"; '
                    "use EMBEDDING_BACKEND=fake only for tests"
                ) from exc
            self.device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
            try:
                self._model = SentenceTransformer(
                    self.model_name, device=self.device, local_files_only=True
                )
            except Exception as exc:
                if not self.allow_download:
                    raise RuntimeError(
                        f"Local embedding model {self.model_name!r} is not in the cache. "
                        "Runtime no longer downloads silently. Run "
                        "`python -m core.index.embeddings --download-model` "
                        "or pass `--download-model` / set EMBEDDING_ALLOW_DOWNLOAD=1 "
                        "for an explicit one-time download."
                    ) from exc
                self._model = SentenceTransformer(
                    self.model_name, device=self.device, local_files_only=False
                )
        return np.asarray(
            self._model.encode(
                list(texts),
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )


def get_embedding_provider() -> EmbeddingProvider:
    backend = os.getenv("EMBEDDING_BACKEND", "local")
    if backend == "fake":
        return hash_embeddings
    if backend == "local":
        return LocalEmbeddingProvider()
    raise ValueError(f"Unsupported EMBEDDING_BACKEND: {backend}; choose fake or local")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local embedding model helpers.")
    parser.add_argument(
        "--download-model",
        action="store_true",
        help="Explicitly download EMBEDDING_MODEL into the local HuggingFace cache.",
    )
    parser.add_argument("--model", default=None, help="Override EMBEDDING_MODEL for download.")
    parser.add_argument("--device", default=None, help="Override EMBED_DEVICE for download.")
    args = parser.parse_args(argv)
    if not args.download_model:
        parser.print_help()
        return 2
    download_embedding_model(model_name=args.model, device=args.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
