"""Verify a numeric claim against source chunk texts."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import re
from time import perf_counter
from typing import Literal

from pydantic import BaseModel

from core.models import ToolMetadata, ToolResult

METADATA = ToolMetadata(name="verify_claim", description_zh="核验数字结论", description_en="Verify a numeric claim")
logger = logging.getLogger(__name__)

# Money / percent with optional thousand separators; unit captured when adjacent.
_NUMBER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z])(?P<sign>-)?(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?(?P<pct>%)?"
    r"(?:\s*(?P<unit>亿元|万元|元))?"
)
_CITATION_RE = re.compile(r"\[[^\[\]]+?\s+p\d+\]")
_CALC_MARK_RE = re.compile(r"（据第\s*(?P<page>\d+)\s*页数据计算）")
_PENDING_MARK = "【待核实】"
_MD_HEADING_RE = re.compile(r"(?m)^#{1,6}\s*")
_LIST_BULLET_RE = re.compile(r"(?m)^\s*[\-\*•]\s+")
_LIST_NUMBER_RE = re.compile(r"(?m)^\s*\d+[\.、\)]\s+")
_YEAR_LABEL_RE = re.compile(r"20\d{2}\s*年")
# Page-only tokens like "第 12 页" are not claim figures.
_PAGE_REF_RE = re.compile(r"第\s*\d+\s*页")

# Map Chinese unit to multiplier toward 元.
_UNIT_TO_YUAN = {
    "元": Decimal("1"),
    "万元": Decimal("10000"),
    "亿元": Decimal("100000000"),
}


class VerifyClaimInput(BaseModel):
    claim: str
    source_chunk_ids: list[str]


class VerifyClaimData(BaseModel):
    status: Literal["supported", "not_found", "mismatch"]
    evidence: list[str]
    difference: str | None = None


VerifyClaimOutput = ToolResult[VerifyClaimData]

ChunkLookup = Callable[[str], str | None] | Mapping[str, str]


@dataclass(frozen=True)
class ParsedNumber:
    """A numeric token normalized for comparison."""

    value: Decimal  # money in 元; percent kept as percent points (12.3 for 12.3%)
    is_percent: bool
    raw: str
    precision: int  # fractional digits in the original token
    unit: str | None


def strip_claim_noise(text: str, *, keep_calc_mark: bool = False) -> str:
    """Remove citation markers, Markdown chrome, and year/page labels before extracting numbers."""
    cleaned = text or ""
    cleaned = _CITATION_RE.sub("", cleaned)
    cleaned = cleaned.replace(_PENDING_MARK, "")
    if not keep_calc_mark:
        cleaned = _CALC_MARK_RE.sub("", cleaned)
    cleaned = _PAGE_REF_RE.sub("", cleaned)
    cleaned = _YEAR_LABEL_RE.sub("", cleaned)
    cleaned = _MD_HEADING_RE.sub("", cleaned)
    cleaned = _LIST_BULLET_RE.sub("", cleaned)
    cleaned = _LIST_NUMBER_RE.sub("", cleaned)
    return cleaned


def _fraction_precision(frac: str | None) -> int:
    if not frac:
        return 0
    return max(0, len(frac) - 1)  # frac includes leading '.'


def parse_number_token(match: re.Match[str]) -> ParsedNumber:
    raw_num = match.group("num").replace(",", "")
    frac = match.group("frac") or ""
    sign = match.group("sign") or ""
    token = f"{sign}{raw_num}{frac}"
    try:
        value = Decimal(token)
    except InvalidOperation as exc:  # pragma: no cover
        raise ValueError(f"invalid number token: {token}") from exc
    is_percent = bool(match.group("pct"))
    unit = match.group("unit")
    precision = _fraction_precision(frac)
    if is_percent:
        return ParsedNumber(value=value, is_percent=True, raw=match.group(0), precision=precision, unit=None)
    if unit:
        value = value * _UNIT_TO_YUAN[unit]
    return ParsedNumber(value=value, is_percent=False, raw=match.group(0), precision=precision, unit=unit)


def extract_parsed_numbers(text: str, *, preprocess: bool = True) -> list[ParsedNumber]:
    """Extract numeric tokens; by default strip citations / Markdown chrome first."""
    source = strip_claim_noise(text) if preprocess else (text or "")
    return [parse_number_token(m) for m in _NUMBER_TOKEN_RE.finditer(source)]


def extract_numbers(text: str) -> list[str]:
    """Return normalized numeric token strings (commas stripped) after noise stripping.

    Kept for backward-compatible call sites; prefer extract_parsed_numbers for matching.
    """
    out: list[str] = []
    for parsed in extract_parsed_numbers(text, preprocess=True):
        if parsed.is_percent:
            out.append(f"{parsed.value}%")
        elif parsed.unit:
            # Represent as base 元 string without unit to keep list simple.
            out.append(format(parsed.value, "f"))
        else:
            out.append(format(parsed.value, "f").rstrip("0").rstrip(".") if "." in format(parsed.value, "f") else format(parsed.value, "f"))
    return out


def _round_to_precision(value: Decimal, precision: int) -> Decimal:
    if precision <= 0:
        quant = Decimal("1")
    else:
        quant = Decimal("1").scaleb(-precision)
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def numbers_equivalent(claim: ParsedNumber, evidence: ParsedNumber) -> bool:
    """Compare by numeric value with unit conversion and percent precision tolerance."""
    if claim.is_percent != evidence.is_percent:
        # Allow claim 12.3% vs evidence 0.123 (ratio form) when evidence has no % but value matches ratio.
        if claim.is_percent and not evidence.is_percent:
            as_ratio = claim.value / Decimal("100")
            # Compare at claim precision on percent scale, or exact ratio.
            if as_ratio == evidence.value:
                return True
            rounded = _round_to_precision(evidence.value * Decimal("100"), claim.precision)
            return rounded == _round_to_precision(claim.value, claim.precision)
        if evidence.is_percent and not claim.is_percent:
            as_ratio = evidence.value / Decimal("100")
            if as_ratio == claim.value:
                return True
            rounded = _round_to_precision(claim.value * Decimal("100"), evidence.precision)
            return rounded == _round_to_precision(evidence.value, evidence.precision)
        return False
    if claim.is_percent:
        # Round both to the coarser precision (min decimals) — typically claim vs evidence original.
        precision = min(claim.precision, evidence.precision) if evidence.precision else claim.precision
        # Review: 12.3% vs 12.30% should pass — round to the fewer decimal places.
        precision = min(claim.precision, evidence.precision) if claim.precision and evidence.precision else max(claim.precision, evidence.precision)
        # Prefer: round the higher-precision one down to the lower-precision one.
        target = min(claim.precision, evidence.precision)
        return _round_to_precision(claim.value, target) == _round_to_precision(evidence.value, target)
    # Money / plain numbers already normalized to 元 when units present.
    if claim.unit or evidence.unit:
        return claim.value == evidence.value
    # Plain numbers: allow precision rounding when one has more decimals.
    if claim.precision != evidence.precision:
        target = min(claim.precision, evidence.precision)
        return _round_to_precision(claim.value, target) == _round_to_precision(evidence.value, target)
    return claim.value == evidence.value


def find_unsupported_numbers(
    claim_numbers: Sequence[ParsedNumber],
    evidence_numbers: Sequence[ParsedNumber],
) -> list[ParsedNumber]:
    """Return claim numbers with no equivalent evidence number. No bare-substring fallback."""
    absent: list[ParsedNumber] = []
    for claim_num in claim_numbers:
        if not any(numbers_equivalent(claim_num, ev) for ev in evidence_numbers):
            absent.append(claim_num)
    return absent


def is_calculated_claim(text: str) -> bool:
    return bool(_CALC_MARK_RE.search(text or ""))


def calc_mark_page(text: str) -> int | None:
    match = _CALC_MARK_RE.search(text or "")
    if not match:
        return None
    return int(match.group("page"))


def _extract_labeled_amount(text: str, labels: Sequence[str]) -> Decimal | None:
    """Find the first amount near any label (元/万元/亿元)."""
    for label in labels:
        pattern = re.compile(
            re.escape(label)
            + r"[^\d]{0,12}(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?(?:\s*(?P<unit>亿元|万元|元))?"
        )
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group("num").replace(",", "") + (match.group("frac") or "")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        unit = match.group("unit") or "元"
        return value * _UNIT_TO_YUAN.get(unit, Decimal("1"))
    return None


def _extract_claimed_ratio(text: str) -> tuple[str | None, ParsedNumber | None]:
    """Detect YoY / gross-margin style claims and the percentage token."""
    cleaned = strip_claim_noise(text, keep_calc_mark=False)
    kind: str | None = None
    if re.search(r"毛利率", cleaned):
        kind = "毛利率"
    elif re.search(r"同比|增速", cleaned):
        kind = "同比"
    elif re.search(r"净利率", cleaned):
        kind = "净利率"
    elif re.search(r"资产负债率", cleaned):
        kind = "资产负债率"
    if kind is None:
        return None, None
    # Prefer an explicit percent token.
    for match in _NUMBER_TOKEN_RE.finditer(cleaned):
        parsed = parse_number_token(match)
        if parsed.is_percent:
            return kind, parsed
    return kind, None


def recalculate_ratio(kind: str, evidence_text: str) -> Decimal | None:
    """Recompute a ratio from evidence text; returns percent points (e.g. 41.51 for 41.51%)."""
    joined = evidence_text
    if kind == "毛利率":
        revenue = _extract_labeled_amount(joined, ("营业收入", "营业总收入", "收入"))
        cost = _extract_labeled_amount(joined, ("营业成本", "成本"))
        if revenue is None or cost is None or revenue == 0:
            return None
        return (revenue - cost) / revenue * Decimal("100")
    if kind == "同比":
        current = _extract_labeled_amount(joined, ("本期", "当年", "本报告期", "营业收入"))
        previous = _extract_labeled_amount(joined, ("上期", "上年", "上年同期", "去年"))
        if current is None or previous is None or previous == 0:
            return None
        return (current - previous) / abs(previous) * Decimal("100")
    if kind == "净利率":
        profit = _extract_labeled_amount(joined, ("净利润",))
        revenue = _extract_labeled_amount(joined, ("营业收入", "营业总收入"))
        if profit is None or revenue is None or revenue == 0:
            return None
        return profit / revenue * Decimal("100")
    if kind == "资产负债率":
        liabilities = _extract_labeled_amount(joined, ("总负债", "负债合计", "负债总额"))
        assets = _extract_labeled_amount(joined, ("总资产", "资产总计", "资产总额"))
        if liabilities is None or assets is None or assets == 0:
            return None
        return liabilities / assets * Decimal("100")
    return None


def verify_calculated_sentence(claim: str, evidence_texts: Sequence[str]) -> tuple[Literal["supported", "mismatch", "not_found"], str | None]:
    """Recalculate YoY / margin style claims marked with （据第 X 页数据计算）."""
    kind, claimed = _extract_claimed_ratio(claim)
    if kind is None or claimed is None:
        return "not_found", "calculated claim missing ratio or percent"
    joined = "\n".join(evidence_texts)
    recomputed = recalculate_ratio(kind, joined)
    if recomputed is None:
        return "not_found", f"unable to recalculate {kind} from evidence"
    rounded = _round_to_precision(recomputed, claimed.precision)
    target = _round_to_precision(claimed.value, claimed.precision)
    if rounded == target:
        return "supported", None
    return "mismatch", f"{kind} claimed {claimed.raw} but recalculated {format(rounded, 'f')}%"


def debug_verify_sentence(
    claim: str,
    evidence_texts: Sequence[str],
) -> dict:
    """Return a JSON-serializable breakdown for one sentence (used by verify-debug export)."""
    cleaned = strip_claim_noise(claim)
    claim_nums = extract_parsed_numbers(claim, preprocess=True)
    evidence_nums: list[ParsedNumber] = []
    for text in evidence_texts:
        evidence_nums.extend(extract_parsed_numbers(text, preprocess=True))
    calculated = is_calculated_claim(claim)
    if calculated:
        status, difference = verify_calculated_sentence(claim, evidence_texts)
    elif not claim_nums:
        status, difference = "supported", None
    else:
        absent = find_unsupported_numbers(claim_nums, evidence_nums)
        if not absent:
            status, difference = "supported", None
        else:
            status, difference = (
                "mismatch",
                "numbers not found in evidence: " + ", ".join(a.raw for a in absent),
            )
    return {
        "sentence": claim,
        "cleaned": cleaned,
        "claim_numbers": [p.raw for p in claim_nums],
        "evidence_numbers": [p.raw for p in evidence_nums],
        "evidence_preview": [t[:200] for t in evidence_texts],
        "calculated": calculated,
        "calc_page": calc_mark_page(claim),
        "status": status,
        "difference": difference,
    }


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
    """Check claim numbers against evidence using numeric equality (units / percent precision)."""
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
        elif is_calculated_claim(claim):
            status, difference = verify_calculated_sentence(claim, evidence)
            result = VerifyClaimOutput(
                ok=True,
                data=VerifyClaimData(status=status, evidence=evidence, difference=difference),
            )
        else:
            claim_numbers = extract_parsed_numbers(claim, preprocess=True)
            if not claim_numbers:
                # No digits left after stripping citations / chrome — pass when evidence exists.
                result = VerifyClaimOutput(
                    ok=True,
                    data=VerifyClaimData(status="supported", evidence=evidence),
                )
            else:
                evidence_numbers: list[ParsedNumber] = []
                for text in evidence:
                    evidence_numbers.extend(extract_parsed_numbers(text, preprocess=True))
                absent = find_unsupported_numbers(claim_numbers, evidence_numbers)
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
                            difference="numbers not found in evidence: "
                            + ", ".join(a.raw for a in absent),
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
