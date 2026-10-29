"""Narrow corrections for two contradictory disclosure-denial sentence shapes.

Only the current section's actually cited chunks are consulted. This is not a
general semantic verifier; absent/partial/ambiguous evidence leaves text intact.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import re
from collections import defaultdict

from core.qa.answer import parse_citation_markers
from core.tools.verify_claim import split_claim_sentences

_CITE = re.compile(r"\[[^\[\]]+?\s+p\d+\]")
_AMOUNT = r"(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}"
_STRUCTURE = re.compile(
    r"检索片段未包含分部报告或(?P<dimensions>分(?:行业|产品|地区)(?:、分(?:行业|产品|地区))*)"
    r"收入明细；分部收入结构【待核实】。"
)
_MARGIN = re.compile(
    rf"分行业表中，(?P<label>[^，；。]{{1,30}})营业收入为(?P<revenue>{_AMOUNT})元，"
    rf"营业成本为(?P<cost>{_AMOUNT})元；该片段未完整显示对应毛利率及同比增减数值，"
    r"毛利率相关结论【待核实】。"
)


def correct_disclosure_denials(markdown: str, hits) -> tuple[str, list[str]]:
    """Correct only explicit table contradictions; retain genuine uncertainty."""
    pages: dict[tuple[str, int], list[str]] = defaultdict(list)
    for hit in hits:
        data = hit if isinstance(hit, dict) else hit.model_dump()
        pages[(data['file'], int(data['page']))].append(data['text'])
    notes: list[str] = []
    out = markdown
    for sentence in split_claim_sentences(markdown):
        markers = set(parse_citation_markers(sentence))
        if len(markers) != 1:
            continue
        file, page = next(iter(markers))
        chunks = pages.get((file, page), [])
        if not chunks:
            continue
        plain = re.sub(r"\s+", "", _CITE.sub("", sentence))
        cite = f"[{file} p{page}]"
        structure = _STRUCTURE.fullmatch(plain)
        replacement = None
        if structure:
            dimensions = structure['dimensions'].split('、')
            # A heading alone (e.g. TOC or clipped table) is not evidence.
            # Require a labeled amount within each actual chunk, never join
            # unrelated chunks to fabricate a table row.
            if all(any(re.search(
                rf"(?:^|\n)\s*{dimension}\s*\n\s*[^\d\n]{{1,40}}\s*\n\s*{_AMOUNT}(?![\d.%])",
                chunk,
            ) for chunk in chunks) for dimension in dimensions):
                replacement = f"引用片段列示了{'、'.join(dimensions)}收入明细{cite}。"
        margin = _MARGIN.fullmatch(plain)
        if margin:
            revenue = Decimal(margin['revenue'].replace(',', ''))
            cost = Decimal(margin['cost'].replace(',', ''))
            # A complete labeled row plus headers in one actual chunk. Do not
            # stitch a trailing percent from another chunk onto this row.
            for chunk in chunks:
                if not all(word in chunk for word in ('营业收入', '营业成本', '毛利率')):
                    continue
                row = re.search(
                    rf"(?:^|\n)\s*{re.escape(margin['label'])}\s*\n\s*"
                    rf"{re.escape(margin['revenue'])}\s*\n\s*{re.escape(margin['cost'])}"
                    r"\s*\n\s*(?P<pct>\d+(?:\.\d+)?)%(?!\d)", chunk)
                if row is None or revenue <= 0:
                    continue
                calculated = ((revenue-cost)/revenue*100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                if abs(calculated-Decimal(row['pct'])) > Decimal('.01'):
                    continue
                replacement = (
                    f"分行业表中，{margin['label']}营业收入为{margin['revenue']}元，"
                    f"营业成本为{margin['cost']}元，毛利率为{row['pct']}%{cite}。"
                    f"同比增减数值仍需核对【待核实】{cite}。"
                )
                break
        if replacement:
            out = out.replace(sentence, replacement, 1)
            notes.append(f"disclosure_guard:corrected:{file}:p{page}")
    return out, notes
