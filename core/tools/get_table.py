"""Read a table by id or keyword from the parsed-document registry."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field

from core.models import Source, ToolMetadata, ToolResult
from core.parse.models import ParsedTable
from core.parse.store import get_document

METADATA = ToolMetadata(name="get_table", description_zh="读取表格", description_en="Read a table")
logger = logging.getLogger(__name__)


class GetTableInput(BaseModel):
    doc_id: str
    table_id: str | None = None
    keyword: str | None = None


class GetTableData(BaseModel):
    headers: list[str]
    rows: list[list[str | float | None]]
    page: int = Field(ge=1)
    raw_text: str | None = None
    table_id: str | None = None


GetTableOutput = ToolResult[GetTableData]


def _match_table(tables: list[ParsedTable], *, table_id: str | None, keyword: str | None) -> ParsedTable | None:
    if table_id:
        for table in tables:
            if table.table_id == table_id:
                return table
        return None
    assert keyword is not None
    key = keyword.strip().lower()
    for table in tables:
        hay = " ".join(
            [
                table.caption or "",
                " ".join(table.headers),
                table.raw_text or "",
            ]
        ).lower()
        if key and key in hay:
            return table
    return None


def get_table(request: GetTableInput) -> GetTableOutput:
    started = perf_counter()
    try:
        doc_id = (request.doc_id or "").strip()
        if not doc_id:
            raise ValueError("doc_id is required")
        if not request.table_id and not (request.keyword and request.keyword.strip()):
            raise ValueError("provide table_id or keyword")
        if request.table_id and request.keyword:
            raise ValueError("provide only one of table_id or keyword")
        document = get_document(doc_id)
        if document is None:
            raise KeyError(f"document not found in registry: {doc_id}")
        table = _match_table(document.tables, table_id=request.table_id, keyword=request.keyword)
        if table is None:
            # Fallback: return raw page snippet if keyword search fails completely.
            if request.keyword:
                for page in document.pages:
                    if request.keyword in page.text:
                        result = GetTableOutput(
                            ok=True,
                            data=GetTableData(
                                headers=[],
                                rows=[],
                                page=page.page,
                                raw_text=page.text[:2000],
                                table_id=None,
                            ),
                            sources=[Source(file=document.file, page=page.page, chunk_id=f"{doc_id}:p{page.page}")],
                        )
                        break
                else:
                    raise LookupError(f"table not found for keyword={request.keyword!r}")
            else:
                raise LookupError(f"table not found: {request.table_id}")
        else:
            result = GetTableOutput(
                ok=True,
                data=GetTableData(
                    headers=list(table.headers),
                    rows=[list(row) for row in table.rows],
                    page=table.page,
                    raw_text=table.raw_text,
                    table_id=table.table_id,
                ),
                sources=[Source(file=document.file, page=table.page, chunk_id=table.table_id)],
            )
    except Exception as exc:
        result = GetTableOutput(ok=False, error=f"{type(exc).__name__}: {exc}")
    logger.info(
        "tool=get_table doc_id=%s elapsed_seconds=%.6f ok=%s",
        request.doc_id,
        perf_counter() - started,
        result.ok,
    )
    return result
