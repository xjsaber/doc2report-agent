"""Registration and invocation logging contracts, without dispatch logic."""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from core.models import ToolMetadata


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
    """Return registered tools; registration is deferred until implementation."""
    raise NotImplementedError("Step 1: registry contract only")
