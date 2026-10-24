"""Render a report section: contracts only, no business logic."""


from pydantic import BaseModel

from core.models import Fact, ToolMetadata, ToolResult

METADATA = ToolMetadata(name="render_section", description_zh="渲染报告章节", description_en="Render a report section")


class RenderSectionInput(BaseModel):
    section_name: str
    template_id: str
    facts: list[Fact]


class RenderSectionData(BaseModel):
    markdown: str


RenderSectionOutput = ToolResult[RenderSectionData]


def render_section(request: RenderSectionInput) -> RenderSectionOutput:
    raise NotImplementedError("Step 1: render_section contract only")
