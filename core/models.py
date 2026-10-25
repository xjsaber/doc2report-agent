"""Shared data contracts. Page numbers are one-based."""

from typing import Generic, Literal, Self, TypeVar

from pydantic import BaseModel, Field, model_validator

SearchMode = Literal["hybrid", "vector", "bm25"]
T = TypeVar("T")


class Source(BaseModel):
    file: str
    page: int = Field(ge=1)
    chunk_id: str


class Chunk(Source):
    doc_id: str
    text: str
    section: str | None = None
    page_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_page_range(self) -> Self:
        if self.page_end is None:
            self.page_end = self.page
        if self.page_end < self.page:
            raise ValueError("page_end must be greater than or equal to page")
        return self


class SearchHit(Chunk):
    score: float


class ToolResult(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: str | None = None
    sources: list[Source] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.ok and self.error is not None:
            raise ValueError("successful results must not contain an error")
        if not self.ok and (self.error is None or not self.error.strip()):
            raise ValueError("failed results must contain a non-empty error")
        if not self.ok and self.data is not None:
            raise ValueError("failed results must not contain data")
        return self


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
