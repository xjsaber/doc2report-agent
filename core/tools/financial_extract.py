"""Structured extraction of key financial rows from annual-report chunk text.

Write-time calc context (``core.graph.workflow``) and verify-time recalculation
(``core.tools.verify_claim``) share these rules so a wrong pick cannot "confirm itself":

* A label only counts when it starts a data row: ``营业收入（元）``, ``营业收入合计``,
  ``营业收入为 5.46 亿元``. Compounds such as ``营业收入构成`` / ``占营业收入比重`` /
  ``营业收入扣除金额`` / ``扣除非经常性损益的净利润`` are rejected.
* Labels may be wrapped across lines by PDF extraction (``净利\\n润``).
* 4-digit years (1900-2099) with no thousands separator, decimals or unit are never
  amounts, nor are ``2024 年`` / ``2024 年度`` / ``第 N 页`` / percentages; column-header
  words (本期、上年同期、金额…) between the label and the numbers are skipped.
* Extraction is per chunk, so a label at the end of one chunk never grabs the first
  number (often a year header) of the next chunk.
* Unit comes from the label ``（万元）``, the number suffix, or the nearest preceding
  ``单位：万元`` header inside the same chunk; default 元.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any

UNIT_TO_YUAN: dict[str, Decimal] = {
    "元": Decimal("1"),
    "万元": Decimal("10000"),
    "亿元": Decimal("100000000"),
}

# Priority order matters: more specific labels first.
METRIC_LABELS: dict[str, tuple[str, ...]] = {
    "营业收入": ("营业总收入", "营业收入"),
    "营业成本": ("营业总成本", "营业成本"),
    "净利润": (
        "合并净利润",
        "净利润",
        "归属于上市公司股东的净利润",
        "归属于母公司所有者的净利润",
        "归属于母公司股东的净利润",
    ),
    "经营活动现金流": ("经营活动产生的现金流量净额",),
    "总资产": ("资产总计", "资产总额", "总资产"),
    "总负债": ("负债合计", "负债总额", "总负债"),
}

# If any of these appears right before a label occurrence, it is a different line item.
_REJECT_PREFIXES: tuple[str, ...] = ("占", "扣除", "非经常性损益的", "流动", "少数股东", "其他")

_LABEL_SUFFIX_RE = re.compile(
    r"(?:合计|总额)?\s*"
    r"(?:[（(]\s*(?:单位\s*[:：]\s*)?(?:人民币)?\s*(?P<lunit>亿元|万元|元)\s*[）)])?\s*"
    r"(?:为|达到|达|约|共计|是|[:：])?\s*"
)

_NUMBER_RE = re.compile(
    r"(?P<sign>[-－−])?\s*(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?"
    r"(?P<pct>\s*%)?(?:\s*(?P<unit>亿元|万元|元))?"
)
# Things that may sit between a label and its numbers (table column headers, year headers).
_PCT_HEAD = r"\s*(?:[（(]\s*%\s*[）)])?"
_FILLER_RE = re.compile(
    r"(?:\s+|"
    # Change columns of the 主要会计数据 table (longest first): 本年比上年增减(%) / 增减变动幅度(%) / 同比增减.
    r"(?:本年|本期|本报告期)(?:末)?比上年(?:同期|度末|末)?增减" + _PCT_HEAD + r"|"
    r"增减变动幅度" + _PCT_HEAD + r"|(?:同比)?增减" + _PCT_HEAD + r"|"
    r"(?:19|20)\d{2}\s*年(?:度|末|初)?|本报告期末|本报告期|上年同期|上年度|本年度|本年|上年|"
    r"本期|上期|同期|期末|期初|金额|单位\s*[:：]\s*(?:人民币)?\s*(?:亿元|万元|元)|[|｜])"
)
_UNIT_HEADER_RE = re.compile(r"单位\s*[:：]\s*(?:人民币)?\s*(?P<unit>亿元|万元|元)")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_NOT_AMOUNT_FOLLOW_RE = re.compile(r"\s*(?:年|月|日|页|季度|个|家|人|名|项|倍|股)")

MAX_SCAN_CHARS = 200
MAX_VALUES = 4


@dataclass(frozen=True)
class FinancialRow:
    """One extracted row: label + current/previous amounts in 元, with its real source."""

    metric: str
    label: str
    current: Decimal
    previous: Decimal | None
    unit: str
    file: str
    page: int
    chunk_id: str


def label_pattern(label: str) -> re.Pattern[str]:
    """Allow PDF line wraps / spaces between label characters (``净利\\n润``)."""
    return re.compile(r"\s*".join(re.escape(ch) for ch in label))


def is_year_token(text: str) -> bool:
    """True for a bare 4-digit year such as ``2024`` (no separator, decimals, %, or unit)."""
    return bool(_YEAR_RE.fullmatch(text.strip()))


def _unit_header_before(text: str, pos: int) -> str | None:
    unit = None
    for match in _UNIT_HEADER_RE.finditer(text, 0, pos):
        unit = match.group("unit")
    return unit


def _prefix_rejected(text: str, start: int) -> bool:
    before = re.sub(r"\s+", "", text[max(0, start - 16) : start])
    return (
        any(before.endswith(prefix) for prefix in _REJECT_PREFIXES)
        or "扣除" in before[-12:]
        or "归属于" in before
    )


def _scan_amounts(text: str, pos: int) -> tuple[list[tuple[Decimal, str | None]], int]:
    """Read consecutive number cells after ``pos``; stop at the first non-number content."""
    values: list[tuple[Decimal, str | None]] = []
    end = min(len(text), pos + MAX_SCAN_CHARS)
    while pos < end and len(values) < MAX_VALUES:
        filler = _FILLER_RE.match(text, pos)
        if filler and filler.end() > pos:
            pos = filler.end()
            continue
        match = _NUMBER_RE.match(text, pos)
        if not match:
            break
        pos = match.end()
        if match.group("pct"):
            # Percent cells (同比 / 占比) are not amounts; keep scanning the row.
            continue
        num, frac, unit = match.group("num"), match.group("frac"), match.group("unit")
        if not unit and not frac and is_year_token(num):
            continue  # bare year header inside the row
        if not unit and _NOT_AMOUNT_FOLLOW_RE.match(text, pos):
            break  # 3 月 / 12 页 / 5 家 …
        if match.start() > 0 and text[match.start() - 1] == "第":
            break
        raw = num.replace(",", "") + (frac or "")
        try:
            value = Decimal(raw)
        except InvalidOperation:  # pragma: no cover
            break
        if match.group("sign"):
            value = -value
        values.append((value, unit))
    return values, pos


def extract_row(text: str, labels: Sequence[str]) -> tuple[str, list[tuple[Decimal, str]]] | None:
    """Return (label, [(value_in_yuan, unit), ...]) for the first valid row of any label."""
    for label in labels:
        for occ in label_pattern(label).finditer(text):
            if _prefix_rejected(text, occ.start()):
                continue
            suffix = _LABEL_SUFFIX_RE.match(text, occ.end())
            pos = suffix.end() if suffix else occ.end()
            # Label must be followed by numbers/whitespace/fillers, not more CJK (构成、比重、扣除…).
            label_unit = suffix.group("lunit") if suffix else None
            cells, _ = _scan_amounts(text, pos)
            if not cells:
                continue
            header_unit = _unit_header_before(text, occ.start())
            out: list[tuple[Decimal, str]] = []
            for value, cell_unit in cells:
                unit = cell_unit or label_unit or header_unit or "元"
                out.append((value * UNIT_TO_YUAN[unit], unit))
            return label, out
    return None


def _hit_fields(hit: Any) -> tuple[str, str, int, str]:
    if isinstance(hit, str):
        return hit, "", 1, ""
    if isinstance(hit, Mapping):
        data = hit
    elif hasattr(hit, "model_dump"):
        data = hit.model_dump()
    else:
        data = {"text": getattr(hit, "text", ""), "file": getattr(hit, "file", ""),
                "page": getattr(hit, "page", 1), "chunk_id": getattr(hit, "chunk_id", "")}
    return (
        str(data.get("text") or ""),
        str(data.get("file") or ""),
        int(data.get("page") or 1),
        str(data.get("chunk_id") or ""),
    )


_QUARTER_LABEL_RE = re.compile(r"第\s*[一二三四1-4]\s*季度|[一二三四]季度|Q[1-4]\b")


def is_quarterly_table(text: str) -> bool:
    """True for 分季度 tables (≥2 distinct quarter headers): their columns are quarters, not 本期/上期."""
    labels = {re.sub(r"\s+", "", m.group(0)) for m in _QUARTER_LABEL_RE.finditer(text or "")}
    return len(labels) >= 2


_PARENT_ATTRIBUTABLE_LABELS = (
    "归属于上市公司股东的净利润",
    "归属于母公司所有者的净利润",
    "归属于母公司股东的净利润",
)


def is_parent_attributable_profit_label(label: str | None) -> bool:
    """True when the extracted profit row is attributable-to-parent, not consolidated."""
    if not label:
        return False
    compact = re.sub(r"\s+", "", label)
    if "合并" in compact:
        return False
    if compact in {re.sub(r"\s+", "", item) for item in _PARENT_ATTRIBUTABLE_LABELS}:
        return True
    return "归属于" in compact and "净利润" in compact


def extract_financial_rows(hits: Iterable[Any], metrics: Iterable[str] | None = None) -> dict[str, FinancialRow]:
    """Extract the first valid row per metric from chunks (dicts, models, or plain strings)."""
    wanted = list(metrics) if metrics is not None else list(METRIC_LABELS)
    items = [_hit_fields(hit) for hit in hits]
    rows: dict[str, FinancialRow] = {}
    for metric in wanted:
        labels = METRIC_LABELS[metric]
        # Label priority first (e.g. 合并净利润 before 归母), then scan chunks.
        chosen = None
        for label in labels:
            for text, file, page, chunk_id in items:
                if is_quarterly_table(text):
                    continue
                found = extract_row(text, (label,))
                if found is None:
                    continue
                matched_label, cells = found
                current, unit = cells[0]
                previous = cells[1][0] if len(cells) > 1 else None
                chosen = FinancialRow(
                    metric=metric,
                    label=matched_label,
                    current=current,
                    previous=previous,
                    unit=unit,
                    file=file,
                    page=page,
                    chunk_id=chunk_id,
                )
                break
            if chosen is not None:
                break
        if chosen is not None:
            rows[metric] = chosen
    return rows


# Ratios outside these bounds (percent points) are treated as extraction errors: never
# injected into the write prompt and never reported as "supported" by verify.
RATIO_BOUNDS: dict[str, tuple[Decimal, Decimal]] = {
    "毛利率": (Decimal("-100"), Decimal("100")),
    "净利率": (Decimal("-100"), Decimal("100")),
    "资产负债率": (Decimal("0"), Decimal("100")),
}


def ratio_is_plausible(name: str, percent: Decimal) -> bool:
    bounds = RATIO_BOUNDS.get(name)
    if bounds is None:
        return True
    low, high = bounds
    return low <= percent <= high
