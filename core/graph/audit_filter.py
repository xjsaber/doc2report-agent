"""Detect generic audit-report boilerplate so risk / conclusion sections don't cite it.

The auditor's report in every annual report contains standard wording such as
"未来的事项或情况可能导致…不能持续经营" inside "注册会计师对财务报表审计的责任".
That is the auditor describing its procedures, not a company-specific risk. For the
risk and conclusion chapters these chunks are excluded (demoted to the end only if
nothing else was retrieved). Company-specific key audit matters (事项描述 / 审计应对)
are kept.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import re
from typing import Any

# Template sections that must not turn audit boilerplate into "关注点".
AUDIT_SENSITIVE_SECTIONS: frozenset[str] = frozenset({"风险因素", "结论"})

_AUDIT_SECTION_RE = re.compile(
    r"审计报告|审计意见|形成审计意见的基础|管理层和治理层对财务报表的责任|"
    r"注册会计师对财务报表审计的责任|审计师(?:的)?责任"
)
_AUDIT_PHRASES: tuple[str, ...] = (
    "注册会计师审计准则",
    "注册会计师职业道德守则",
    "合理保证",
    "职业判断",
    "职业怀疑",
    "审计证据",
    "重大错报",
    "治理层",
    "不能持续经营",
    "持续经营假设",
    "鉴证结论",
    "发表审计意见",
    "我们不对这些事项单独发表意见",
    "审计报告日",
)


def _field(hit: Any, name: str) -> str:
    if isinstance(hit, dict):
        return str(hit.get(name) or "")
    return str(getattr(hit, name, "") or "")


def is_audit_boilerplate(text: str, section: str | None = None) -> bool:
    """True for auditor's-report standard paragraphs (opinion, basis, responsibilities)."""
    if section and _AUDIT_SECTION_RE.search(section):
        return True
    body = re.sub(r"\s+", "", text or "")
    hits = sum(1 for phrase in _AUDIT_PHRASES if phrase in body)
    return hits >= 2


def demote_audit_boilerplate(hits: Iterable[Any]) -> list[Any]:
    """Return non-boilerplate hits first; boilerplate only kept if nothing else exists."""
    items = list(hits)
    kept = [h for h in items if not is_audit_boilerplate(_field(h, "text"), _field(h, "section"))]
    if kept:
        return kept
    return items


def section_needs_audit_filter(section_name: str, sensitive: Sequence[str] | None = None) -> bool:
    names = AUDIT_SENSITIVE_SECTIONS if sensitive is None else frozenset(sensitive)
    return section_name in names


AUDIT_PROMPT_RULE = (
    "审计报告中的通用段落（审计意见、形成审计意见的基础、管理层和治理层的责任、注册会计师的责任，"
    "以及其中「可能导致不能持续经营」「合理保证」「重大错报」等准则标准措辞）不是公司特有的风险或关注点，"
    "不得写成风险或结论。"
)
