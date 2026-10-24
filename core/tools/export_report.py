"""Export a report: contracts only, no business logic."""

from typing import Literal

from pydantic import BaseModel, Field

from core.models import ToolMetadata, ToolResult

METADATA = ToolMetadata(name="export_report", description_zh="导出报告", description_en="Export a report")


class ExportReportInput(BaseModel):
    report_md: str
    format: Literal["docx", "md"]
    title: str


class ExportReportData(BaseModel):
    file_path: str


ExportReportOutput = ToolResult[ExportReportData]


def export_report(request: ExportReportInput) -> ExportReportOutput:
    raise NotImplementedError("Step 1: export_report contract only")
