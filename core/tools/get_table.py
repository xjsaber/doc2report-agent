"""Read a table: contracts only, no business logic."""

from typing import Literal

from pydantic import BaseModel, Field

from core.models import ToolMetadata, ToolResult

METADATA = ToolMetadata(name="get_table", description_zh="读取表格", description_en="Read a table")


class GetTableInput(BaseModel):
    # Exactly one selector will be checked by the future implementation.
    doc_id: str
    table_id: str | None = None
    keyword: str | None = None


class GetTableData(BaseModel):
    headers: list[str]
    rows: list[list[str | float | None]]
    page: int = Field(ge=1)
    raw_text: str | None = None


GetTableOutput = ToolResult[GetTableData]


def get_table(request: GetTableInput) -> GetTableOutput:
    raise NotImplementedError("Step 1: get_table contract only")
