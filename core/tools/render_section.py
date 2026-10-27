"""Render a report section as Markdown with [file pN] citations."""

from __future__ import annotations

import logging
from time import perf_counter

from pydantic import BaseModel

from core.models import Fact, Source, ToolMetadata, ToolResult

METADATA = ToolMetadata(name="render_section", description_zh="渲染报告章节", description_en="Render a report section")
logger = logging.getLogger(__name__)


class RenderSectionInput(BaseModel):
    section_name: str
    template_id: str
    facts: list[Fact]


class RenderSectionData(BaseModel):
    markdown: str


RenderSectionOutput = ToolResult[RenderSectionData]


def _citation_labels(sources: list[Source]) -> str:
    labels: list[str] = []
    seen: set[str] = set()
    for source in sources:
        label = f"[{source.file} p{source.page}]"
        if label not in seen:
            seen.add(label)
            labels.append(label)
    return " ".join(labels)


def render_section(request: RenderSectionInput) -> RenderSectionOutput:
    started = perf_counter()
    try:
        name = (request.section_name or "").strip()
        if not name:
            raise ValueError("section_name is required")
        if not (request.template_id or "").strip():
            raise ValueError("template_id is required")
        if not request.facts:
            raise ValueError("facts must not be empty")
        lines = [f"## {name}", ""]
        sources: list[Source] = []
        for fact in request.facts:
            text = (fact.text or "").strip()
            if not text:
                raise ValueError("fact text must not be empty")
            if not fact.sources:
                raise ValueError("each fact requires at least one source")
            labels = _citation_labels(fact.sources)
            # Keep existing markers; otherwise append labels once.
            if "[" in text and " p" in text:
                lines.append(text)
            else:
                lines.append(f"{text} {labels}".rstrip())
            lines.append("")
            sources.extend(fact.sources)
        markdown = "\n".join(lines).rstrip() + "\n"
        result = RenderSectionOutput(
            ok=True,
            data=RenderSectionData(markdown=markdown),
            sources=sources,
        )
    except Exception as exc:
        result = RenderSectionOutput(ok=False, error=f"{type(exc).__name__}: {exc}")
    logger.info(
        "tool=render_section section=%s template_id=%s elapsed_seconds=%.6f ok=%s",
        request.section_name,
        request.template_id,
        perf_counter() - started,
        result.ok,
    )
    return result
