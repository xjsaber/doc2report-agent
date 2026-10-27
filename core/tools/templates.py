"""Template discovery and loading from templates/*.yaml."""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter

import yaml
from pydantic import BaseModel, ValidationError

from core.models import ReportTemplate, ToolMetadata, ToolResult

LIST_METADATA = ToolMetadata(name="list_templates", description_zh="列出模板", description_en="List templates")
LOAD_METADATA = ToolMetadata(name="load_template", description_zh="加载模板", description_en="Load a template")
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


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


def templates_dir() -> Path:
    return _TEMPLATES_DIR


def _load_yaml_template(path: Path) -> ReportTemplate:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"template must be a mapping: {path.name}")
    return ReportTemplate.model_validate(raw)


def list_templates(request: ListTemplatesInput | None = None) -> ListTemplatesOutput:
    started = perf_counter()
    request = request or ListTemplatesInput()
    try:
        templates: list[ReportTemplate] = []
        if _TEMPLATES_DIR.is_dir():
            for path in sorted(_TEMPLATES_DIR.glob("*.yaml")):
                templates.append(_load_yaml_template(path))
        result = ListTemplatesOutput(ok=True, data=ListTemplatesData(templates=templates))
    except Exception as exc:
        result = ListTemplatesOutput(ok=False, error=f"{type(exc).__name__}: {exc}")
    logger.info(
        "tool=list_templates elapsed_seconds=%.6f ok=%s",
        perf_counter() - started,
        result.ok,
    )
    return result


def load_template(request: LoadTemplateInput) -> LoadTemplateOutput:
    started = perf_counter()
    try:
        template_id = (request.template_id or "").strip()
        if not template_id:
            raise ValueError("template_id is required")
        path = _TEMPLATES_DIR / f"{template_id}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"template not found: {template_id}")
        template = _load_yaml_template(path)
        if template.template_id != template_id:
            raise ValueError(
                f"template_id mismatch: file={template_id} content={template.template_id}"
            )
        result = LoadTemplateOutput(ok=True, data=LoadTemplateData(template=template))
    except Exception as exc:
        result = LoadTemplateOutput(ok=False, error=f"{type(exc).__name__}: {exc}")
    logger.info(
        "tool=load_template template_id=%s elapsed_seconds=%.6f ok=%s",
        request.template_id,
        perf_counter() - started,
        result.ok,
    )
    return result
