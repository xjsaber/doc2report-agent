"""Retrieve-then-answer with mandatory [file pN] citations; refuse when empty."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
import os
import re

from core.index.retriever import Retriever
from core.models import SearchHit
from core.qa.llm import ChatMessage, ChatModel, build_chat_model
from core.tools.search_chunks import SearchChunksInput, search_chunks


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


_SYSTEM = (
    "你是严谨的文档问答助手。只根据用户提供的检索片段作答；"
    "不得编造片段中没有的事实或数字。"
    "每条关键结论后必须标注引用，格式严格为 [文件名 p页码]，例如 [report.pdf p3]。"
    "若片段不足以回答，明确说明无法从资料中找到依据，不要猜测。"
)

_CITATION_RE = re.compile(r"\[[^\]]+\s+p\d+\]")


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


def _ensure_citation_markers(answer: str, citations: Sequence[Citation]) -> str:
    """Append missing required markers once; never invent new page numbers."""
    if not citations:
        return answer
    missing = [c.label for c in citations if c.label not in answer]
    if not missing:
        return answer
    return answer.rstrip() + "\n\n参考：" + " ".join(dict.fromkeys(missing))


def answer_question(
    question: str,
    *,
    retriever: Retriever,
    chat_model: ChatModel | None = None,
    doc_ids: Sequence[str] | None = None,
    top_k: int = 8,
    mode: str = "hybrid",
    auto_build_model: bool = True,
) -> AnswerResult:
    """Hybrid retrieve then answer. Refuses when no hits; retrieval-only without API key."""
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

    hits = tool.data.chunks if tool.data else []
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
        "请用中文回答，并在依据处标注 [文件名 p页码]。"
    )
    raw = model.complete(
        [
            ChatMessage(role="system", content=_SYSTEM),
            ChatMessage(role="user", content=user_prompt),
        ]
    )
    answer = _ensure_citation_markers(raw, citations)
    if not _CITATION_RE.search(answer):
        return AnswerResult(
            question=query,
            answer=None,
            citations=citations,
            refused=True,
            message="模型回答缺少引用标记，已拒绝展示以避免无依据内容。",
        )
    return AnswerResult(question=query, answer=answer, citations=citations)
