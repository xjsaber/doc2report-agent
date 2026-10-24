"""Parse a document: contracts only, no business logic."""

from typing import Literal

from pydantic import BaseModel, Field

from core.models import ToolMetadata, ToolResult

METADATA = ToolMetadata(name="parse_document", description_zh="解析文档", description_en="Parse a document")


class ParseDocumentInput(BaseModel):
    file_path: str
    engine: Literal["pymupdf", "mineru"] = "pymupdf"


class Section(BaseModel):
    title: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)


class TableSummary(BaseModel):
    table_id: str
    page: int = Field(ge=1)
    caption: str | None = None


class ParseDocumentData(BaseModel):
    doc_id: str
    pages: int = Field(ge=1)
    sections: list[Section]
    tables: list[TableSummary]


ParseDocumentOutput = ToolResult[ParseDocumentData]


def parse_document(request: ParseDocumentInput) -> ParseDocumentOutput:
    raise NotImplementedError("Step 1: parse_document contract only")
