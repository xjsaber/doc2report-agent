"""Shared data contracts. Page numbers are one-based."""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

SearchMode = Literal["hybrid", "vector", "bm25"]
T = TypeVar("T")


class Source(BaseModel):
    file: str
    page: int = Field(ge=1)
    chunk_id: str


class Chunk(Source):
    doc_id: str
    text: str


class SearchHit(Source):
    text: str
    score: float


class ToolResult(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: str | None = None
    sources: list[Source] = Field(default_factory=list)


class ToolMetadata(BaseModel):
    name: str
    description_zh: str
    description_en: str
    version: str = "0.1.0"


class Fact(BaseModel):
    text: str
    sources: list[Source]


class TemplateSection(BaseModel):
    name: str
    questions: list[str]
    keywords: list[str]


class ReportTemplate(BaseModel):
    template_id: str
    title: str
    sections: list[TemplateSection]
