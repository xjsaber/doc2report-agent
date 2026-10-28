"""LangGraph report workflow: plan → retrieve → write → verify → assemble."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Any, Literal
import re

from langgraph.graph import END, StateGraph

from core.graph.state import ReportState, SectionState
from core.index.retriever import Retriever
from core.models import Fact, SearchHit, Source
from core.qa.answer import parse_citation_markers, validate_answer_citations, Citation
from core.qa.llm import ChatMessage, ChatModel
from core.tools.search_chunks import SearchChunksInput, search_chunks
from core.tools.templates import LoadTemplateInput, load_template
from core.tools.verify_claim import (
    VerifyClaimInput,
    strip_claim_noise,
    verify_claim,
)
from core.tools.calc_financials import (
    CalcFinancialsInput,
    MetricValue,
    PeriodValues,
    calc_financials,
)
from decimal import Decimal, InvalidOperation

_PENDING_MARK = "【待核实】"
_CITATION_LINE_RE = re.compile(r"\[[^\[\]]+?\s+p\d+\]")


def _empty_section(name: str, questions: list[str], keywords: list[str]) -> SectionState:
    return SectionState(
        name=name,
        questions=questions,
        keywords=keywords,
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



def _try_build_calc_context(section: SectionState) -> str:
    """Best-effort: pull amounts from retrieved chunks and run calc_financials for write context."""
    texts: list[str] = []
    for hit in section.get("chunks") or []:
        data = hit if isinstance(hit, dict) else hit.model_dump()
        texts.append(str(data.get("text") or ""))
    joined = "\n".join(texts)
    if not joined.strip():
        return ""

    unit_mult = {"元": Decimal("1"), "万元": Decimal("10000"), "亿元": Decimal("100000000")}

    def _amount(labels: tuple[str, ...]) -> tuple[Decimal, int] | None:
        for label in labels:
            pattern = re.compile(
                re.escape(label)
                + r"[^\d]{0,12}(?P<sign>-)?(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?"
                + r"(?:\s*(?P<unit>亿元|万元|元))?"
            )
            match = pattern.search(joined)
            if not match:
                continue
            raw = (match.group("sign") or "") + match.group("num").replace(",", "") + (match.group("frac") or "")
            try:
                value = Decimal(raw)
            except InvalidOperation:
                continue
            unit = match.group("unit") or "元"
            page = 1
            for hit in section.get("chunks") or []:
                data = hit if isinstance(hit, dict) else hit.model_dump()
                if label in data["text"] and match.group("num") in data["text"].replace(",", ""):
                    page = int(data["page"])
                    break
            return value * unit_mult[unit], page
        return None

    revenue = _amount(("营业收入", "营业总收入"))
    cost = _amount(("营业成本",))
    profit = _amount(("净利润",))
    values: dict = {}
    if revenue is not None:
        amount, page = revenue
        values["营业收入"] = PeriodValues(
            current=MetricValue(value=amount, sources=[Source(file="context", page=page, chunk_id="calc")])
        )
    if cost is not None:
        amount, page = cost
        values["营业成本"] = PeriodValues(
            current=MetricValue(value=amount, sources=[Source(file="context", page=page, chunk_id="calc")])
        )
    if profit is not None:
        amount, page = profit
        values["净利润"] = PeriodValues(
            current=MetricValue(value=amount, sources=[Source(file="context", page=page, chunk_id="calc")])
        )
    if len(values) < 2:
        return ""
    result = calc_financials(CalcFinancialsInput(values=values))
    if not result.ok or result.data is None:
        return ""
    lines = ["已用 calc_financials 根据片段数字算出的比率（写作时必须引用这些结果，禁止自行心算）："]
    for metric in result.data.metrics:
        if metric.value is None:
            continue
        pct = (metric.value * Decimal("100")).quantize(Decimal("0.01"))
        page = metric.sources[0].page if metric.sources else 1
        lines.append(f"- {metric.name} = {pct}% （据第 {page} 页数据计算）；公式：{metric.formula}")
    return "\n".join(lines)


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
        "同比、毛利率、净利率、资产负债率等比率禁止自行心算，必须使用写作上下文中 calc_financials 的结果，"
        "并在该句末尾标注「（据第 X 页数据计算）」（X 为计算所用原文页码）。"
        "若关键数字无法在片段中确认，可先写结论并等待核验。"
    )
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
            _empty_section(sec.name, list(sec.questions), list(sec.keywords))
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
        for section in sections:
            query = _format_retrieve_query(section)  # type: ignore[arg-type]
            tool = search_chunks(
                SearchChunksInput(query=query, doc_ids=doc_ids, top_k=top_k, mode="hybrid"),
                retriever=retriever,
            )
            if not tool.ok:
                errors.append(f"retrieve:{section['name']}:{tool.error}")
                section["chunks"] = []
                continue
            hits = tool.data.chunks if tool.data else []
            section["chunks"] = hits
            section["sources"] = [
                Source(file=h.file, page=h.page, chunk_id=h.chunk_id) for h in hits
            ]
            section["facts"] = [
                Fact(
                    text=h.text,
                    sources=[Source(file=h.file, page=h.page, chunk_id=h.chunk_id)],
                )
                for h in hits
            ]
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
            if not raw.startswith("##"):
                body = raw
                raw = f"## {section['name']}\n\n{body}\n"
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
            for sentence in re.split(r"(?<=[。！？\n])", md):
                piece = sentence.strip()
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
        for section in state.get("sections") or []:
            md = section.get("markdown") or f"## {section.get('name')}\n"
            parts.append(md.rstrip())
            parts.append("")
        report_md = "\n".join(parts).rstrip() + "\n"
        return {"report_md": report_md, "stage": "assemble"}

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
