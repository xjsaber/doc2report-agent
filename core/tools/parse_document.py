"""Parse and chunk a local PDF using the shared tool result envelope."""

import logging
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field

from core.models import Chunk, Source, ToolMetadata, ToolResult
from core.parse import Section, chunk_document, parse_pdf

logger = logging.getLogger(__name__)

METADATA = ToolMetadata(name="parse_document", description_zh="解析文档", description_en="Parse a document")


class ParseDocumentInput(BaseModel):
    file_path: str
    engine: Literal["pymupdf", "mineru"] = "pymupdf"


class TableSummary(BaseModel):
    table_id: str
    page: int = Field(ge=1)
    caption: str | None = None


class ParseDocumentData(BaseModel):
    doc_id: str
    pages: int = Field(ge=1)
    sections: list[Section]
    tables: list[TableSummary]
    chunks: list[Chunk] = Field(default_factory=list)
    engine: Literal["pymupdf", "mineru"] = "pymupdf"


ParseDocumentOutput = ToolResult[ParseDocumentData]


def parse_document(request: ParseDocumentInput) -> ParseDocumentOutput:
    started = perf_counter()
    try:
        document = parse_pdf(request.file_path, engine=request.engine)
        chunks = chunk_document(document)
        result = ParseDocumentOutput(
            ok=True,
            data=ParseDocumentData(
                doc_id=document.doc_id, pages=len(document.pages), sections=document.sections,
                tables=[TableSummary(table_id=t.table_id, page=t.page, caption=t.caption)
                        for t in document.tables],
                chunks=chunks, engine=document.engine,
            ),
            sources=[Source(file=c.file, page=c.page, chunk_id=c.chunk_id) for c in chunks],
        )
    except Exception as exc:
        logger.warning("parse_document failed (%s): %s", type(exc).__name__, exc)
        result = ParseDocumentOutput(ok=False, error=f"{type(exc).__name__}: {exc}")
    logger.info(
        "tool=parse_document file=%s engine=%s elapsed_seconds=%.6f ok=%s",
        Path(request.file_path).name, request.engine, perf_counter() - started, result.ok,
    )
    return result
