"""LangGraph-compatible state schema; no graph or node execution yet."""

from typing import Literal, TypedDict

from core.models import Fact, ReportTemplate, SearchHit, Source


class SectionState(TypedDict):
    name: str
    questions: list[str]
    keywords: list[str]
    chunks: list[SearchHit]
    facts: list[Fact]
    markdown: str
    verification_status: Literal["pending", "supported", "not_found", "mismatch"]
    verification_notes: list[str]
    needs_verification: bool
    rewrite_count: Literal[0, 1]
    sources: list[Source]
    elapsed_seconds: float
    input_tokens: int
    output_tokens: int


class ReportState(TypedDict, total=False):
    doc_ids: list[str]
    template_id: str
    template: ReportTemplate
    title: str
    sections: list[SectionState]
    current_section_index: int
    stage: Literal["plan", "retrieve", "write", "verify", "assemble"]
    report_md: str
    export_paths: list[str]
    errors: list[str]
