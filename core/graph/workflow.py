"""LangGraph report workflow: plan → retrieve → write → verify → assemble."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Any, Literal
import re

from langgraph.graph import END, StateGraph

from core.graph.audit_filter import AUDIT_PROMPT_RULE, demote_audit_boilerplate, section_needs_audit_filter
from core.graph.state import ReportState, SectionState
from core.index.retriever import Retriever
from core.models import Fact, SearchHit, Source
from core.qa.answer import parse_citation_markers, validate_answer_citations, Citation
from core.qa.llm import ChatMessage, ChatModel
from core.tools.search_chunks import SearchChunksInput, search_chunks
from core.tools.templates import LoadTemplateInput, load_template
from core.tools.verify_claim import (
    VerifyClaimInput,
    split_claim_sentences,
    strip_claim_noise,
    verify_claim,
)
from core.tools.calc_financials import (
    CalcFinancialsInput,
    MetricValue,
    PeriodValues,
    calc_financials,
)
from decimal import Decimal

from core.tools.financial_extract import extract_financial_rows, is_parent_attributable_profit_label, ratio_is_plausible

_PENDING_MARK = "【待核实】"
_CITATION_LINE_RE = re.compile(r"\[[^\[\]]+?\s+p\d+\]")


def _empty_section(
    name: str,
    questions: list[str],
    keywords: list[str],
    section_hints: list[str] | None = None,
) -> SectionState:
    return SectionState(
        name=name,
        questions=questions,
        keywords=keywords,
        section_hints=list(section_hints or []),
        chunks=[],
        facts=[],
        markdown="",
        verification_status="pending",
        verification_notes=[],
        needs_verification=False,
        rewrite_count=0,
        sources=[],
        elapsed_seconds=0.0,
        input_tokens=0,
        output_tokens=0,
    )


def _hits_to_citations(hits: Sequence[SearchHit]) -> list[Citation]:
    return [
        Citation(
            file=h.file,
            page=h.page,
            chunk_id=h.chunk_id,
            text=h.text,
            score=h.score,
            doc_id=h.doc_id,
            section=h.section,
        )
        for h in hits
    ]


def _chunk_lookup_from_sections(sections: Sequence[SectionState]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for section in sections:
        for hit in section["chunks"]:
            # SearchHit may be dict (TypedDict serialization) or model.
            if isinstance(hit, dict):
                lookup[hit["chunk_id"]] = hit["text"]
            else:
                lookup[hit.chunk_id] = hit.text
    return lookup


def _format_retrieve_query(section: SectionState) -> str:
    parts = list(section["questions"]) + list(section["keywords"])
    return " ".join(parts)


def _merge_search_hits(*groups: Sequence) -> list:
    """Deduplicate SearchHit-like objects by chunk_id; earlier groups win order."""
    seen: set[str] = set()
    out: list = []
    for group in groups:
        for hit in group or []:
            data = hit if isinstance(hit, dict) else hit.model_dump()
            cid = str(data.get("chunk_id") or "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            out.append(hit)
    return out



_BS_METRIC_TOKENS = ("资产总计", "负债合计", "合并资产负债表")


def _hit_data(hit) -> dict:
    return hit if isinstance(hit, dict) else hit.model_dump()


def _expand_balance_sheet_neighbor_chunks(
    hits: Sequence,
    *,
    retriever,
    doc_ids: Sequence[str] | None,
    page_span: int = 2,
) -> list:
    """When 合并资产负债表 is recalled, pull same-doc chunks on nearby pages with 资产总计/负债合计.

    Statement tables often start on the titled page and put totals one–two pages later;
    hybrid search rarely ranks those total lines. Uses ``retriever._chunks`` when present
    (MemoryRetriever); otherwise a no-op.
    """
    stored = getattr(retriever, "_chunks", None)
    if not isinstance(stored, dict) or not stored:
        return list(hits)
    anchors: list[int] = []
    for hit in hits:
        data = _hit_data(hit)
        blob = f"{data.get('section') or ''}\n{data.get('text') or ''}"
        if "合并资产负债表" in blob:
            try:
                anchors.append(int(data.get("page") or 0))
            except (TypeError, ValueError):
                continue
    if not anchors:
        return list(hits)
    target_pages = {p + d for p in anchors if p > 0 for d in range(0, page_span + 1)}
    allowed = None if doc_ids is None else set(doc_ids)
    extras: list = []
    for chunk in stored.values():
        if allowed is not None and chunk.doc_id not in allowed:
            continue
        if int(getattr(chunk, "page", 0) or 0) not in target_pages:
            continue
        text = getattr(chunk, "text", "") or ""
        if not any(tok in text for tok in ("资产总计", "负债合计")):
            continue
        extras.append(SearchHit(**chunk.model_dump(), score=1.0))
    if not extras:
        return list(hits)
    return _merge_search_hits(extras, hits)


def _try_build_calc_context(section: SectionState) -> str:
    """Best-effort: extract key rows from retrieved chunks and run calc_financials for write context.

    Shares ``extract_financial_rows`` with verify so both sides use one set of rules
    (years / page numbers / percentages are never amounts; per-chunk extraction; real
    file/page/chunk_id as sources). Implausible ratios are dropped: better nothing than
    a wrong number the writer is told to copy.
    """
    hits = list(section.get("chunks") or [])
    if not hits:
        return ""
    rows = extract_financial_rows(hits)
    values: dict = {}
    for metric, row in rows.items():
        source = Source(file=row.file or "unknown", page=max(1, row.page), chunk_id=row.chunk_id or "unknown")
        previous = (
            MetricValue(value=row.previous, sources=[source]) if row.previous is not None else None
        )
        values[metric] = PeriodValues(current=MetricValue(value=row.current, sources=[source]), previous=previous)
    if not values:
        return ""
    result = calc_financials(CalcFinancialsInput(values=values))
    if not result.ok or result.data is None:
        return ""
    # Map metric display name; annotate net margin when profit input is 归母口径.
    profit_row = rows.get("净利润")
    parent_scope = bool(profit_row and is_parent_attributable_profit_label(profit_row.label))
    lines: list[str] = []
    for metric in result.data.metrics:
        if metric.value is None:
            continue
        pct = (metric.value * Decimal("100")).quantize(Decimal("0.01"))
        if not ratio_is_plausible(metric.name, pct):
            continue
        pages = sorted({s.page for s in metric.sources})
        page_text = "、".join(str(p) for p in pages) if pages else "?"
        display = metric.name
        formula = metric.formula
        if metric.name == "净利率" and parent_scope:
            display = "净利率（归母净利润口径）"
            formula = "归母净利润 / 营业收入"
        lines.append(
            f"- {display} = {pct}% （据第 {pages[0]} 页数据计算）；公式：{formula}；所用页码：{page_text}"
        )
    if not lines:
        return ""
    return "\n".join(
        [
            "已根据检索片段数字算出的比率（写作时必须引用这些结果，禁止自行心算；"
            "正文不要出现内部工具名或「写作上下文」字样）：",
            *lines,
        ]
    )


def _write_prompt(section: SectionState) -> list[ChatMessage]:
    blocks: list[str] = []
    for index, hit in enumerate(section["chunks"], start=1):
        data = hit if isinstance(hit, dict) else hit.model_dump()
        blocks.append(
            f"[{index}] 文件={data['file']} 页码={data['page']} chunk_id={data['chunk_id']}\n{data['text']}"
        )
    context = "\n\n".join(blocks) if blocks else "（无检索片段）"
    calc_context = _try_build_calc_context(section)  # type: ignore[arg-type]
    system = (
        "你是年报分析写作者。只根据检索片段撰写该章节；"
        "每条含事实的句子后必须标注 [文件名 p页码]；"
        "不得编造片段中没有的数字或结论。"
        "同比、毛利率、净利率、资产负债率等比率禁止自行心算，必须使用下方「已根据检索片段数字算出的比率」中的结果，"
        "并在该句末尾标注「（据第 X 页数据计算）」（X 为计算所用原文页码）。"
        "若净利率标注为「归母净利润口径」，正文必须写明「归母净利润口径」，不要写成「销售净利率」。"
        "正文禁止出现 calc_financials、「写作上下文」、内部函数名或工具名。"
        "若相关数字无法在片段中确认，可先写结论并等待核验。"
    )
    if section_needs_audit_filter(str(section.get("name") or "")):
        system += AUDIT_PROMPT_RULE
    calc_block = f"\n\n{calc_context}\n" if calc_context else "\n"
    user = (
        f"章节：{section['name']}\n"
        f"需要回答的问题：{'；'.join(section['questions'])}\n\n"
        f"检索片段：\n{context}"
        f"{calc_block}\n"
        "请输出该章节 Markdown 正文（不要重复一级标题）。"
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def _rewrite_prompt(section: SectionState, notes: Sequence[str]) -> list[ChatMessage]:
    base = _write_prompt(section)
    note_text = "；".join(notes) if notes else "引用或数字未通过核验"
    base.append(
        ChatMessage(
            role="user",
            content=(
                f"上一稿未通过核验：{note_text}。\n"
                f"请重写，确保所有 [文件 p页码] 均来自检索片段，且数字能在被引片段中找到；"
                f"仍无法核实的数字请标注{_PENDING_MARK}。"
            ),
        )
    )
    return base



_INTERNAL_TERM_RES: tuple[re.Pattern[str], str] = (
    (re.compile(r"写作上下文\s*calc_financials\s*给出?", re.IGNORECASE), ""),
    (re.compile(r"写作上下文\s*", re.IGNORECASE), ""),
    (re.compile(r"\bcalc_financials\b", re.IGNORECASE), "财务比率计算"),
    (re.compile(r"销售净利率"), "净利率"),
)


def sanitize_internal_terms(markdown: str) -> tuple[str, list[str]]:
    """Strip internal tool/prompt words from report body; return (text, warnings)."""
    warnings: list[str] = []
    out = markdown or ""
    for pattern, repl in _INTERNAL_TERM_RES:
        if pattern.search(out):
            warnings.append(f"removed_or_replaced:{pattern.pattern}")
            out = pattern.sub(repl, out)
    # Collapse awkward doubled spaces left by deletions (keep newlines).
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out, warnings


_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def normalize_section_markdown(name: str, raw: str) -> str:
    """Guarantee exactly one ``## {name}`` chapter heading at the top.

    r8 E2E: the writer sometimes opened with its own ``## 子标题``, which used to be
    kept as-is, so the chapter title (e.g. 「公司概况」) vanished from md/docx.
    Writer headings are demoted below the chapter level (``#``/``##`` -> ``###``).
    """
    lines = (raw or "").strip().splitlines()
    if lines:
        first = _HEADING_LINE_RE.match(lines[0].strip())
        if first and first.group(2).strip().strip("#").strip() == name:
            lines = lines[1:]
    body: list[str] = []
    for line in lines:
        match = _HEADING_LINE_RE.match(line)
        if match and len(match.group(1)) <= 2:
            line = f"### {match.group(2)}"
        body.append(line)
    text = "\n".join(body).strip()
    return f"## {name}\n\n{text}\n" if text else f"## {name}\n"


def build_report_graph(
    *,
    retriever: Retriever,
    chat_model: ChatModel,
    top_k: int = 6,
):
    """Compile plan→retrieve→write→verify→assemble. Model and retriever are injected."""

    def plan_node(state: ReportState) -> dict[str, Any]:
        template_id = state.get("template_id") or "company_analysis"
        loaded = load_template(LoadTemplateInput(template_id=template_id))
        if not loaded.ok or loaded.data is None:
            return {
                "errors": list(state.get("errors") or []) + [loaded.error or "load_template failed"],
                "stage": "plan",
            }
        template = loaded.data.template
        sections = [
            _empty_section(
                sec.name,
                list(sec.questions),
                list(sec.keywords),
                list(getattr(sec, "section_hints", None) or []),
            )
            for sec in template.sections
        ]
        return {
            "template_id": template.template_id,
            "template": template,
            "title": state.get("title") or template.title,
            "sections": sections,
            "current_section_index": 0,
            "stage": "plan",
            "errors": list(state.get("errors") or []),
        }

    def retrieve_node(state: ReportState) -> dict[str, Any]:
        doc_ids = state.get("doc_ids")
        sections = [dict(s) for s in (state.get("sections") or [])]
        errors = list(state.get("errors") or [])

        def _section_match(hit_section: str | None, hints: list[str]) -> bool:
            if not hints:
                return False
            label = (hit_section or "").strip()
            if not label:
                return False
            for hint in hints:
                hint = (hint or "").strip()
                if not hint:
                    continue
                if hint in label or label in hint:
                    return True
            return False

        def _metric_text_match(hit_text: str | None, hints: list[str]) -> bool:
            """Prefer chunks whose body carries statement totals named in hints."""
            text = hit_text or ""
            if not text or not hints:
                return False
            hint_set = {h.strip() for h in hints if (h or "").strip()}
            for tok in _BS_METRIC_TOKENS:
                if tok in hint_set and tok in text:
                    return True
            return False

        def _prefer_hinted(hits: list, hints: list[str], limit: int) -> list:
            if not hints:
                return list(hits)[:limit]
            preferred = []
            rest = []
            for hit in hits:
                data = hit if isinstance(hit, dict) else hit.model_dump()
                if _section_match(data.get("section"), hints) or _metric_text_match(
                    data.get("text"), hints
                ):
                    preferred.append(hit)
                else:
                    rest.append(hit)
            chosen = preferred[:limit]
            if len(chosen) < max(1, limit // 2):
                # Not enough in-hint hits — fill from global remainder.
                for hit in rest:
                    if len(chosen) >= limit:
                        break
                    chosen.append(hit)
            elif len(chosen) < limit:
                for hit in rest:
                    if len(chosen) >= limit:
                        break
                    chosen.append(hit)
            return chosen

        for section in sections:
            query = _format_retrieve_query(section)  # type: ignore[arg-type]
            hints = list(section.get("section_hints") or [])
            # Over-fetch then prefer chunks whose section title matches hints.
            fetch_k = max(top_k * 3, top_k)
            tool = search_chunks(
                SearchChunksInput(query=query, doc_ids=doc_ids, top_k=fetch_k, mode="hybrid"),
                retriever=retriever,
            )
            if not tool.ok:
                errors.append(f"retrieve:{section['name']}:{tool.error}")
                section["chunks"] = []
                continue
            raw_hits = list(tool.data.chunks if tool.data else [])
            # Supplemental pass: section_hints alone often recall TOC-titled pages
            # (e.g. 合并资产负债表) that the long question+keyword query buries.
            hint_query = " ".join(h for h in hints if (h or "").strip())
            if hint_query:
                hint_tool = search_chunks(
                    SearchChunksInput(
                        query=hint_query, doc_ids=doc_ids, top_k=fetch_k, mode="hybrid"
                    ),
                    retriever=retriever,
                )
                if hint_tool.ok and hint_tool.data:
                    raw_hits = _merge_search_hits(hint_tool.data.chunks, raw_hits)
                elif not hint_tool.ok:
                    errors.append(f"retrieve-hints:{section['name']}:{hint_tool.error}")
            # Balance-sheet title page → also keep total lines on the next pages.
            raw_hits = _expand_balance_sheet_neighbor_chunks(
                raw_hits, retriever=retriever, doc_ids=doc_ids
            )
            if section_needs_audit_filter(str(section.get("name") or "")):
                # Auditor's-report standard wording is not a company risk / conclusion.
                raw_hits = demote_audit_boilerplate(raw_hits)
            hits = _prefer_hinted(raw_hits, hints, top_k)
            section["chunks"] = hits
            section["sources"] = [
                Source(file=h.file, page=h.page, chunk_id=h.chunk_id)
                if not isinstance(h, dict)
                else Source(file=h["file"], page=h["page"], chunk_id=h["chunk_id"])
                for h in hits
            ]
            section["facts"] = []
            for h in hits:
                data = h if isinstance(h, dict) else h.model_dump()
                section["facts"].append(
                    Fact(
                        text=data["text"],
                        sources=[Source(file=data["file"], page=data["page"], chunk_id=data["chunk_id"])],
                    )
                )
        return {"sections": sections, "stage": "retrieve", "errors": errors}

    def write_node(state: ReportState) -> dict[str, Any]:
        sections = [dict(s) for s in (state.get("sections") or [])]
        errors = list(state.get("errors") or [])
        for section in sections:
            needs = bool(section.get("needs_verification"))
            has_md = bool((section.get("markdown") or "").strip())
            # First pass writes every section; rewrite pass only touches flagged ones.
            if has_md and not needs:
                continue
            started = perf_counter()
            notes = list(section.get("verification_notes") or [])
            if not section.get("chunks"):
                section["markdown"] = f"## {section['name']}\n\n（本章暂无检索依据）\n"
                section["elapsed_seconds"] = perf_counter() - started
                continue
            messages = _rewrite_prompt(section, notes) if needs else _write_prompt(section)  # type: ignore[arg-type]
            try:
                raw = chat_model.complete(messages).strip()
            except Exception as exc:  # pragma: no cover - injected fakes
                errors.append(f"write:{section['name']}:{exc}")
                raw = ""
            raw = normalize_section_markdown(section["name"], raw)
            section["markdown"] = raw if raw.endswith("\n") else raw + "\n"
            section["needs_verification"] = False
            section["elapsed_seconds"] = float(section.get("elapsed_seconds") or 0) + (
                perf_counter() - started
            )
        return {"sections": sections, "stage": "write", "errors": errors}

    def verify_node(state: ReportState) -> dict[str, Any]:
        sections = [dict(s) for s in (state.get("sections") or [])]
        lookup = _chunk_lookup_from_sections(sections)  # type: ignore[arg-type]
        for section in sections:
            md = section.get("markdown") or ""
            hits = section.get("chunks") or []
            citations = _hits_to_citations(hits)  # type: ignore[arg-type]
            notes: list[str] = []
            status: Literal["pending", "supported", "not_found", "mismatch"] = "supported"

            if not hits:
                section["verification_status"] = "not_found"
                section["verification_notes"] = ["无检索片段"]
                continue

            ok, err = validate_answer_citations(md, citations)
            if not ok:
                status = "not_found"
                notes.append(err or "引用校验失败")

            # Numeric claims: digits remaining after stripping citations / Markdown chrome.
            for piece in split_claim_sentences(md):
                if not piece:
                    continue
                if _PENDING_MARK in piece:
                    continue
                if not re.search(r"\d", strip_claim_noise(piece)):
                    continue
                markers = parse_citation_markers(piece)
                chunk_ids: list[str] = []
                for file_name, page in markers:
                    for hit in hits:
                        data = hit if isinstance(hit, dict) else hit.model_dump()
                        if data["file"] == file_name and int(data["page"]) == page:
                            chunk_ids.append(data["chunk_id"])
                if not chunk_ids:
                    # Fall back to all section chunks when sentence has digits but markers already failed.
                    chunk_ids = [
                        (h["chunk_id"] if isinstance(h, dict) else h.chunk_id) for h in hits
                    ]
                checked = verify_claim(
                    VerifyClaimInput(claim=piece, source_chunk_ids=chunk_ids),
                    chunk_lookup=lookup,
                )
                if not checked.ok or checked.data is None:
                    status = "not_found"
                    notes.append(checked.error or "verify_claim failed")
                    continue
                if checked.data.status != "supported":
                    status = checked.data.status
                    notes.append(checked.data.difference or checked.data.status)
                    # Mark the sentence for rewrite / pending.
                    if _PENDING_MARK not in piece:
                        md = md.replace(piece, f"{piece}{_PENDING_MARK}", 1)

            rewrite_count = int(section.get("rewrite_count") or 0)
            if status != "supported" and rewrite_count < 1:
                section["needs_verification"] = True
                section["rewrite_count"] = 1  # type: ignore[typeddict-item]
                section["verification_status"] = status
                section["verification_notes"] = notes
                section["markdown"] = md
            elif status != "supported":
                # Second failure: keep 待核实 markers.
                if _PENDING_MARK not in md:
                    md = md.rstrip() + f"\n\n{_PENDING_MARK} 部分数字未能在引用原文中核验。\n"
                section["needs_verification"] = False
                section["verification_status"] = status
                section["verification_notes"] = notes
                section["markdown"] = md if md.endswith("\n") else md + "\n"
            else:
                section["needs_verification"] = False
                section["verification_status"] = "supported"
                section["verification_notes"] = []
                section["markdown"] = md if md.endswith("\n") else md + "\n"

        return {
            "sections": sections,
            "stage": "verify",
            "errors": list(state.get("errors") or []),
        }

    def assemble_node(state: ReportState) -> dict[str, Any]:
        title = state.get("title") or "年报分析"
        parts = [f"# {title}", ""]
        errors = list(state.get("errors") or [])
        for section in state.get("sections") or []:
            md = section.get("markdown") or f"## {section.get('name')}\n"
            cleaned, warnings = sanitize_internal_terms(md)
            for warning in warnings:
                errors.append(f"assemble:sanitize:{section.get('name')}:{warning}")
            parts.append(cleaned.rstrip())
            parts.append("")
        report_md = "\n".join(parts).rstrip() + "\n"
        report_md, top_warnings = sanitize_internal_terms(report_md)
        for warning in top_warnings:
            errors.append(f"assemble:sanitize:report:{warning}")
        return {"report_md": report_md, "stage": "assemble", "errors": errors}

    def route_after_verify(state: ReportState) -> str:
        for section in state.get("sections") or []:
            if section.get("needs_verification"):
                return "write"
        return "assemble"

    graph = StateGraph(ReportState)
    graph.add_node("plan", plan_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("write", write_node)
    graph.add_node("verify", verify_node)
    graph.add_node("assemble", assemble_node)
    graph.set_entry_point("plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "write")
    graph.add_edge("write", "verify")
    graph.add_conditional_edges("verify", route_after_verify, {"write": "write", "assemble": "assemble"})
    graph.add_edge("assemble", END)
    return graph.compile()


def run_report(
    *,
    retriever: Retriever,
    chat_model: ChatModel,
    doc_ids: Sequence[str] | None = None,
    template_id: str = "company_analysis",
    title: str | None = None,
    top_k: int = 6,
) -> ReportState:
    """Execute the compiled graph once and return final state."""
    app = build_report_graph(retriever=retriever, chat_model=chat_model, top_k=top_k)
    initial: ReportState = {
        "template_id": template_id,
        "title": title or "",
        "sections": [],
        "current_section_index": 0,
        "stage": "plan",
        "report_md": "",
        "export_paths": [],
        "errors": [],
    }
    if doc_ids is not None:
        initial["doc_ids"] = list(doc_ids)
    return app.invoke(initial)  # type: ignore[return-value]
