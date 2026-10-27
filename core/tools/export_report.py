"""Export a report to Markdown or Word (.docx)."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Literal
import logging

from pydantic import BaseModel, Field

from core.export.markdown_docx import default_output_path, write_docx, write_markdown
from core.models import ToolMetadata, ToolResult

logger = logging.getLogger(__name__)

METADATA = ToolMetadata(name="export_report", description_zh="导出报告", description_en="Export a report")


class ExportReportInput(BaseModel):
    report_md: str
    format: Literal["docx", "md"]
    title: str
    output_dir: str | None = Field(default=None, description="Optional directory; defaults to ./output")


class ExportReportData(BaseModel):
    file_path: str


ExportReportOutput = ToolResult[ExportReportData]


def export_report(request: ExportReportInput) -> ExportReportOutput:
    started = perf_counter()
    title = (request.title or "").strip() or "报告"
    if request.format not in ("docx", "md"):
        return ToolResult(ok=False, error=f"unsupported format: {request.format}")
    if not (request.report_md or "").strip():
        return ToolResult(ok=False, error="report_md is empty")
    try:
        out_dir = Path(request.output_dir).expanduser() if request.output_dir else Path("output")
        target = default_output_path(title, request.format, out_dir=out_dir)
        if request.format == "md":
            path = write_markdown(request.report_md, title=title, path=target)
        else:
            path = write_docx(request.report_md, title=title, path=target)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        elapsed = perf_counter() - started
        logger.info(
            "tool=export_report format=%s elapsed_seconds=%.3f ok=False error=%s",
            request.format,
            elapsed,
            exc,
        )
        return ToolResult(ok=False, error=str(exc))

    elapsed = perf_counter() - started
    logger.info(
        "tool=export_report format=%s elapsed_seconds=%.3f ok=True path=%s",
        request.format,
        elapsed,
        path,
    )
    return ToolResult(ok=True, data=ExportReportData(file_path=str(path)))
