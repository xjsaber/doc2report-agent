"""Retrieve-then-answer with mandatory [file pN] citations; refuse when empty or invalid."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
import os
import re

from core.index.embeddings import EmbeddingProvider
from core.index.relevance import filter_relevant_hits
from core.index.retriever import Retriever
from core.models import SearchHit
from core.qa.llm import ChatMessage, ChatModel, build_chat_model
from core.tools.search_chunks import SearchChunksInput, search_chunks

# Model must emit this exact phrase when evidence is insufficient.
REFUSAL_PHRASE = "资料中未找到依据"

_SYSTEM = (
    "你是严谨的文档问答助手。只根据用户提供的检索片段作答；"
    "不得编造片段中没有的事实或数字。"
    "每条相关结论后必须标注引用，格式严格为 [文件名 p页码]，例如 [report.pdf p3]。"
    f"若片段不足以回答，只输出固定句「{REFUSAL_PHRASE}」，不要猜测，不要附加引用。"
)

# Capture file name and page: [something.pdf p12]
_CITATION_RE = re.compile(r"\[([^\[\]]+?)\s+p(\d+)\]")


@dataclass
class Citation:
    file: str
    page: int
    chunk_id: str
    text: str
    score: float
    doc_id: str
    section: str | None = None

    @property
    def label(self) -> str:
        return f"[{self.file} p{self.page}]"


@dataclass
class AnswerResult:
    question: str
    answer: str | None
    citations: list[Citation] = field(default_factory=list)
    refused: bool = False
    retrieval_only: bool = False
    message: str | None = None


def load_dotenv_config(path: str | Path | None = None) -> dict[str, str]:
    """Load KEY=VALUE pairs from a .env file into os.environ (do not override existing)."""
    env_path = Path(path) if path else Path.cwd() / ".env"
    loaded: dict[str, str] = {}
    if not env_path.is_file():
        return loaded
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if not key:
            continue
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


def _citations_from_hits(hits: Sequence[SearchHit]) -> list[Citation]:
    return [
        Citation(
            file=hit.file,
            page=hit.page,
            chunk_id=hit.chunk_id,
            text=hit.text,
            score=hit.score,
            doc_id=hit.doc_id,
            section=hit.section,
        )
        for hit in hits
    ]


def _format_context(citations: Sequence[Citation]) -> str:
    blocks: list[str] = []
    for index, citation in enumerate(citations, start=1):
        section = f" 章节={citation.section}" if citation.section else ""
        blocks.append(
            f"[{index}] 文件={citation.file} 页码={citation.page}{section}\n{citation.text}"
        )
    return "\n\n".join(blocks)


def parse_citation_markers(text: str) -> list[tuple[str, int]]:
    """Return (file, page) pairs in appearance order."""
    return [(match.group(1).strip(), int(match.group(2))) for match in _CITATION_RE.finditer(text or "")]


def validate_answer_citations(
    answer: str,
    allowed: Sequence[Citation],
) -> tuple[bool, str | None]:
    """Require every [file pN] to appear in this retrieval; refuse if none or any fabricated."""
    allowed_set = {(c.file, c.page) for c in allowed}
    found = parse_citation_markers(answer)
    if not found:
        return False, "模型回答缺少有效引用标记，已拒绝展示以避免无依据内容。"
    for file_name, page in found:
        if (file_name, page) not in allowed_set:
            return False, (
                f"回答含有不在本次检索结果中的引用 [{file_name} p{page}]，"
                "已拒绝展示以避免编造出处。"
            )
    return True, None


def answer_question(
    question: str,
    *,
    retriever: Retriever,
    chat_model: ChatModel | None = None,
    doc_ids: Sequence[str] | None = None,
    top_k: int = 8,
    mode: str = "hybrid",
    auto_build_model: bool = True,
    embedder: EmbeddingProvider | None = None,
    min_vector_score: float | None = None,
) -> AnswerResult:
    """Hybrid retrieve then answer. Refuses when no relevant hits or invalid citations."""
    query = (question or "").strip()
    if not query:
        return AnswerResult(
            question=question or "",
            answer=None,
            refused=True,
            message="请输入问题。",
        )

    tool = search_chunks(
        SearchChunksInput(
            query=query,
            doc_ids=list(doc_ids) if doc_ids is not None else None,
            top_k=top_k,
            mode=mode,  # type: ignore[arg-type]
        ),
        retriever=retriever,
    )
    if not tool.ok:
        return AnswerResult(
            question=query,
            answer=None,
            refused=True,
            message=tool.error or "检索失败",
        )

    raw_hits = tool.data.chunks if tool.data else []
    # Prefer retriever-bound embedder when present so tests stay consistent.
    bound = embedder
    if bound is None and hasattr(retriever, "embedder"):
        bound = getattr(retriever, "embedder")
    # Reuse indexed vectors when the Retriever exposes them (avoids re-encoding hits).
    stored = None
    getter = getattr(retriever, "get_stored_vectors", None)
    if callable(getter) and raw_hits:
        stored = getter([hit.chunk_id for hit in raw_hits])
    hits = filter_relevant_hits(
        query,
        raw_hits,
        embedder=bound,
        min_vector_score=min_vector_score,
        hit_vectors=stored,
    )
    citations = _citations_from_hits(hits)
    if not citations:
        return AnswerResult(
            question=query,
            answer=None,
            citations=[],
            refused=True,
            message="检索未找到相关依据，无法回答，请换个问法或先入库相关 PDF。",
        )

    model = chat_model
    if model is None and auto_build_model:
        model = build_chat_model()

    if model is None:
        preview = "\n\n".join(f"{c.label}\n{c.text}" for c in citations)
        return AnswerResult(
            question=query,
            answer=None,
            citations=citations,
            retrieval_only=True,
            message=(
                "未配置 API_KEY（请在项目根目录 .env 中设置，勿提交到仓库）。"
                "以下仅展示混合检索结果，未调用大模型：\n\n" + preview
            ),
        )

    user_prompt = (
        f"问题：{query}\n\n检索片段：\n{_format_context(citations)}\n\n"
        f"请用中文回答，并在依据处标注 [文件名 p页码]。"
        f"若无法依据片段回答，只输出「{REFUSAL_PHRASE}」。"
    )
    raw = model.complete(
        [
            ChatMessage(role="system", content=_SYSTEM),
            ChatMessage(role="user", content=user_prompt),
        ]
    ).strip()

    if REFUSAL_PHRASE in raw:
        return AnswerResult(
            question=query,
            answer=None,
            citations=citations,
            refused=True,
            message=REFUSAL_PHRASE,
        )

    ok, error = validate_answer_citations(raw, citations)
    if not ok:
        return AnswerResult(
            question=query,
            answer=None,
            citations=citations,
            refused=True,
            message=error,
        )
    return AnswerResult(question=query, answer=raw, citations=citations)
