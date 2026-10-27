"""Retriever selection; native Windows defaults to memory."""

import os
import sys

from core.index.memory import Embedder, MemoryRetriever, hash_embeddings
from core.index.embeddings import EmbeddingProvider
from core.index.retriever import Retriever


def get_retriever(backend: str | None = None, *, embedder: Embedder | None = None,
                  uri: str = "data/index/milvus.db") -> Retriever:
    selected = backend if backend is not None else os.getenv("RETRIEVER")
    selected = selected or ("memory" if sys.platform == "win32" else "milvus")
    if selected == "memory":
        return MemoryRetriever(embedder=embedder)
    if selected == "milvus":
        from core.index.milvus import MilvusRetriever
        return MilvusRetriever(embedder=embedder, uri=uri)
    raise ValueError(f"Unsupported RETRIEVER: {selected}; choose memory or milvus")
