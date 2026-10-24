"""Verify a numeric claim: contracts only, no business logic."""

from typing import Literal

from pydantic import BaseModel, Field

from core.models import ToolMetadata, ToolResult

METADATA = ToolMetadata(name="verify_claim", description_zh="核验数字结论", description_en="Verify a numeric claim")


class VerifyClaimInput(BaseModel):
    claim: str
    source_chunk_ids: list[str]


class VerifyClaimData(BaseModel):
    status: Literal["supported", "not_found", "mismatch"]
    evidence: list[str]
    difference: str | None = None


VerifyClaimOutput = ToolResult[VerifyClaimData]


def verify_claim(request: VerifyClaimInput) -> VerifyClaimOutput:
    raise NotImplementedError("Step 1: verify_claim contract only")
