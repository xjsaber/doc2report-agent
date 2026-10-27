"""Optional BGE-style query instruction prefix (queries only, never documents)."""

from __future__ import annotations

import os

# Official-style short-query prefix for bge-small-zh-v1.5; documents must not use it.
DEFAULT_EMBED_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


def resolve_query_instruction() -> str:
    """Return query prefix. Explicit empty env disables; unset defaults by backend."""
    if "EMBED_QUERY_INSTRUCTION" in os.environ:
        return os.environ["EMBED_QUERY_INSTRUCTION"]
    # Fake embeddings in tests should not be skewed by a long Chinese prefix.
    if os.getenv("EMBEDDING_BACKEND", "local") == "fake":
        return ""
    return DEFAULT_EMBED_QUERY_INSTRUCTION


def apply_query_instruction(query: str) -> str:
    instruction = resolve_query_instruction()
    if not instruction:
        return query
    return f"{instruction}{query}"
