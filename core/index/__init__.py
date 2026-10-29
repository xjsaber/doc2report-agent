"""Retriever selection; default prefers memory; win32 falls back from milvus."""

from __future__ import annotations

import logging
import os
import sys

from core.index.memory import Embedder, MemoryRetriever
from core.index.retriever import Retriever

logger = logging.getLogger(__name__)


def get_retriever(
    backend: str | None = None,
    *,
    embedder: Embedder | None = None,
    uri: str = "data/index/milvus.db",
) -> Retriever:
    selected = backend if backend is not None else os.getenv("RETRIEVER")
    selected = (selected or "").strip().lower() or (
        "memory" if sys.platform == "win32" else "milvus"
    )
    if selected == "memory":
        return MemoryRetriever(embedder=embedder)
    if selected == "milvus":
        if sys.platform == "win32":
            logger.warning(
                "RETRIEVER=milvus is unavailable on native Windows; falling back to memory. "
                "Use Docker/Linux/macOS/WSL for Milvus Lite, or set RETRIEVER=memory."
            )
            return MemoryRetriever(embedder=embedder)
        from core.index.milvus import MilvusRetriever

        return MilvusRetriever(embedder=embedder, uri=uri)
    raise ValueError(f"Unsupported RETRIEVER: {selected}; choose memory or milvus")
