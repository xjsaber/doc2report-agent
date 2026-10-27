"""Tool registration and invocation logging contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from core.models import ToolMetadata
from core.tools import calc_financials as calc_financials_mod
from core.tools import export_report as export_report_mod
from core.tools import get_table as get_table_mod
from core.tools import parse_document as parse_document_mod
from core.tools import render_section as render_section_mod
from core.tools import search_chunks as search_chunks_mod
from core.tools import templates as templates_mod
from core.tools import verify_claim as verify_claim_mod


@dataclass(frozen=True)
class ToolDefinition:
    metadata: ToolMetadata
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[..., BaseModel]


class ToolCallLog(BaseModel):
    tool_name: str
    parameter_summary: str
    elapsed_seconds: float
    ok: bool


def list_tools() -> list[ToolDefinition]:
    """Return registered v1 tools (export_report remains a deferred stub)."""
    return [
        ToolDefinition(
            metadata=parse_document_mod.METADATA,
            input_model=parse_document_mod.ParseDocumentInput,
            output_model=parse_document_mod.ParseDocumentOutput,
            handler=parse_document_mod.parse_document,
        ),
        ToolDefinition(
            metadata=search_chunks_mod.METADATA,
            input_model=search_chunks_mod.SearchChunksInput,
            output_model=search_chunks_mod.SearchChunksOutput,
            handler=search_chunks_mod.search_chunks,
        ),
        ToolDefinition(
            metadata=get_table_mod.METADATA,
            input_model=get_table_mod.GetTableInput,
            output_model=get_table_mod.GetTableOutput,
            handler=get_table_mod.get_table,
        ),
        ToolDefinition(
            metadata=calc_financials_mod.METADATA,
            input_model=calc_financials_mod.CalcFinancialsInput,
            output_model=calc_financials_mod.CalcFinancialsOutput,
            handler=calc_financials_mod.calc_financials,
        ),
        ToolDefinition(
            metadata=verify_claim_mod.METADATA,
            input_model=verify_claim_mod.VerifyClaimInput,
            output_model=verify_claim_mod.VerifyClaimOutput,
            handler=verify_claim_mod.verify_claim,
        ),
        ToolDefinition(
            metadata=render_section_mod.METADATA,
            input_model=render_section_mod.RenderSectionInput,
            output_model=render_section_mod.RenderSectionOutput,
            handler=render_section_mod.render_section,
        ),
        ToolDefinition(
            metadata=export_report_mod.METADATA,
            input_model=export_report_mod.ExportReportInput,
            output_model=export_report_mod.ExportReportOutput,
            handler=export_report_mod.export_report,
        ),
        ToolDefinition(
            metadata=templates_mod.LIST_METADATA,
            input_model=templates_mod.ListTemplatesInput,
            output_model=templates_mod.ListTemplatesOutput,
            handler=templates_mod.list_templates,
        ),
        ToolDefinition(
            metadata=templates_mod.LOAD_METADATA,
            input_model=templates_mod.LoadTemplateInput,
            output_model=templates_mod.LoadTemplateOutput,
            handler=templates_mod.load_template,
        ),
    ]
