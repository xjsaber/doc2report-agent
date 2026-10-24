"""Template discovery and loading: one tool family, two operations."""

from pydantic import BaseModel
from core.models import ReportTemplate, ToolMetadata, ToolResult

LIST_METADATA = ToolMetadata(name="list_templates", description_zh="列出模板", description_en="List templates")
LOAD_METADATA = ToolMetadata(name="load_template", description_zh="加载模板", description_en="Load a template")


class ListTemplatesInput(BaseModel):
    pass


class LoadTemplateInput(BaseModel):
    template_id: str


class ListTemplatesData(BaseModel):
    templates: list[ReportTemplate]


class LoadTemplateData(BaseModel):
    template: ReportTemplate


ListTemplatesOutput = ToolResult[ListTemplatesData]
LoadTemplateOutput = ToolResult[LoadTemplateData]


def list_templates(request: ListTemplatesInput) -> ListTemplatesOutput:
    raise NotImplementedError("Step 1: template listing contract only")


def load_template(request: LoadTemplateInput) -> LoadTemplateOutput:
    raise NotImplementedError("Step 1: template loading contract only")
