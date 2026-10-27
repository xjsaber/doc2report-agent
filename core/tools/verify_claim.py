"""Verify a numeric claim against source chunk texts."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import logging
import re
from time import perf_counter
from typing import Literal

from pydantic import BaseModel

from core.models import ToolMetadata, ToolResult

METADATA = ToolMetadata(name="verify_claim", description_zh="核验数字结论", description_en="Verify a numeric claim")
logger = logging.getLogger(__name__)

# Capture integers/decimals with optional thousand separators or Chinese units nearby.
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?"
)


class VerifyClaimInput(BaseModel):
    claim: str
    source_chunk_ids: list[str]


class VerifyClaimData(BaseModel):
    status: Literal["supported", "not_found", "mismatch"]
    evidence: list[str]
    difference: str | None = None


VerifyClaimOutput = ToolResult[VerifyClaimData]

ChunkLookup = Callable[[str], str | None] | Mapping[str, str]


def extract_numbers(text: str) -> list[str]:
    """Return normalized numeric tokens (commas stripped) in appearance order."""
    found: list[str] = []
    for match in _NUMBER_RE.finditer(text or ""):
        token = match.group(0).replace(",", "")
        found.append(token)
    return found


def _lookup_text(chunk_id: str, lookup: ChunkLookup | None) -> str | None:
    if lookup is None:
        return None
    if callable(lookup):
        return lookup(chunk_id)
    return lookup.get(chunk_id)


def verify_claim(
    request: VerifyClaimInput,
    *,
    chunk_lookup: ChunkLookup | None = None,
) -> VerifyClaimOutput:
    """Pure check: every number in the claim must appear in at least one source chunk text."""
    started = perf_counter()
    try:
        claim = (request.claim or "").strip()
        if not claim:
            raise ValueError("claim is required")
        if not request.source_chunk_ids:
            raise ValueError("source_chunk_ids must not be empty")
        if chunk_lookup is None:
            raise ValueError("chunk_lookup is required to resolve source texts")

        evidence: list[str] = []
        missing_ids: list[str] = []
        for chunk_id in request.source_chunk_ids:
            text = _lookup_text(chunk_id, chunk_lookup)
            if text is None:
                missing_ids.append(chunk_id)
            else:
                evidence.append(text)
        if missing_ids:
            result = VerifyClaimOutput(
                ok=True,
                data=VerifyClaimData(
                    status="not_found",
                    evidence=evidence,
                    difference=f"missing chunk_ids: {', '.join(missing_ids)}",
                ),
            )
        else:
            claim_numbers = extract_numbers(claim)
            if not claim_numbers:
                # No digits to check — treat as supported if evidence exists.
                result = VerifyClaimOutput(
                    ok=True,
                    data=VerifyClaimData(status="supported", evidence=evidence),
                )
            else:
                joined = "\n".join(evidence)
                evidence_numbers = set(extract_numbers(joined))
                # Also accept raw substring presence (handles 1,234 vs 1234 already normalized).
                absent = [n for n in claim_numbers if n not in evidence_numbers and n not in joined]
                if not absent:
                    result = VerifyClaimOutput(
                        ok=True,
                        data=VerifyClaimData(status="supported", evidence=evidence),
                    )
                else:
                    result = VerifyClaimOutput(
                        ok=True,
                        data=VerifyClaimData(
                            status="mismatch",
                            evidence=evidence,
                            difference=f"numbers not found in evidence: {', '.join(absent)}",
                        ),
                    )
    except Exception as exc:
        result = VerifyClaimOutput(ok=False, error=f"{type(exc).__name__}: {exc}")
    logger.info(
        "tool=verify_claim claim_chars=%d chunk_count=%d elapsed_seconds=%.6f ok=%s",
        len(request.claim or ""),
        len(request.source_chunk_ids or []),
        perf_counter() - started,
        result.ok,
    )
    return result
