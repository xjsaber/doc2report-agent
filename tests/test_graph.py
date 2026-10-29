"""LangGraph report flow with fake chat model (no network)."""

from core.graph import run_report
from core.index import get_retriever
from core.models import Chunk
from core.qa import FakeChatModel
from core.tools.templates import ListTemplatesInput, LoadTemplateInput, list_templates, load_template


def _index_sample(retriever):
    chunks = [
        Chunk(
            chunk_id="c1",
            doc_id="doc-a",
            file="synthetic.pdf",
            text="公司概况：本集团专注自主研发软件产品与技术服务，注册地披露于年报。",
            page=2,
            page_end=2,
            section="公司概况",
        ),
        Chunk(
            chunk_id="c2",
            doc_id="doc-a",
            file="synthetic.pdf",
            text="主营业务为软件产品销售与技术服务，报告期收入结构保持稳定。",
            page=3,
            page_end=3,
            section="主营业务",
        ),
        Chunk(
            chunk_id="c3",
            doc_id="doc-a",
            file="synthetic.pdf",
            text="财务表现：营业收入 120.5 亿元，净利润 30.2 亿元。",
            page=4,
            page_end=4,
            section="财务表现",
        ),
        Chunk(
            chunk_id="c4",
            doc_id="doc-a",
            file="synthetic.pdf",
            text="风险因素包括市场竞争加剧与技术迭代风险。",
            page=5,
            page_end=5,
            section="风险因素",
        ),
        Chunk(
            chunk_id="c5",
            doc_id="doc-a",
            file="synthetic.pdf",
            text="综合来看，公司经营总体平稳，需关注研发投入与现金流。",
            page=6,
            page_end=6,
            section="结论",
        ),
    ]
    retriever.index_chunks(chunks)
    return chunks


def _section_reply(name: str, page: int, with_number: str | None = "120.5") -> str:
    number_bit = f"关键数据为 {with_number} 亿元。" if with_number else "本章综合披露信息。"
    return (
        f"本章概述{name}要点。{number_bit}"
        f"[synthetic.pdf p{page}]"
    )


def test_list_and_load_template():
    listed = list_templates(ListTemplatesInput())
    assert listed.ok and listed.data
    ids = {t.template_id for t in listed.data.templates}
    assert "company_analysis" in ids
    loaded = load_template(LoadTemplateInput(template_id="company_analysis"))
    assert loaded.ok and loaded.data
    assert loaded.data.template.title == "年报分析"
    assert len(loaded.data.template.sections) == 5
    missing = load_template(LoadTemplateInput(template_id="no_such_template"))
    assert missing.ok is False


def test_graph_normal_path():
    retriever = get_retriever("memory")
    _index_sample(retriever)

    def factory(messages, index):
        user_blobs = "\n".join(m.content for m in messages)
        mapping = {
            "章节：公司概况": (2, None),
            "章节：主营业务": (3, None),
            "章节：财务表现": (4, "120.5"),
            "章节：风险因素": (5, None),
            "章节：结论": (6, None),
        }
        for key, (page, num) in mapping.items():
            if key in user_blobs:
                name = key.split("：", 1)[1]
                return _section_reply(name, page, with_number=num)
        return _section_reply("结论", 6, with_number=None)

    fake = FakeChatModel(reply_factory=factory)
    state = run_report(retriever=retriever, chat_model=fake, doc_ids=["doc-a"], top_k=4)
    assert state.get("stage") == "assemble"
    assert state.get("report_md")
    assert "年报分析" in state["report_md"] or "公司概况" in state["report_md"]
    assert all(s.get("verification_status") == "supported" for s in state["sections"])
    assert all(int(s.get("rewrite_count") or 0) == 0 for s in state["sections"])
    assert fake.calls  # model used


def test_graph_rewrite_once_then_ok():
    retriever = get_retriever("memory")
    _index_sample(retriever)
    finance_writes = {"n": 0}

    def factory(messages, index):
        # First pass for 财务表现 uses a fabricated number to force rewrite; later passes use 120.5.
        user_blobs = "\n".join(m.content for m in messages)
        if "章节：财务表现" in user_blobs:
            finance_writes["n"] += 1
            if finance_writes["n"] <= 1:
                return "营业收入为 999.9 亿元。[synthetic.pdf p4]"
            return "营业收入为 120.5 亿元。[synthetic.pdf p4]"
        mapping = {
            "章节：公司概况": ("公司概况", 2),
            "章节：主营业务": ("主营业务", 3),
            "章节：风险因素": ("风险因素", 5),
            "章节：结论": ("结论", 6),
        }
        for key, (name, page) in mapping.items():
            if key in user_blobs:
                return _section_reply(name, page, with_number=None)
        return _section_reply("结论", 6, with_number=None)

    fake = FakeChatModel(reply_factory=factory)
    state = run_report(retriever=retriever, chat_model=fake, doc_ids=["doc-a"], top_k=4)
    finance = next(s for s in state["sections"] if s["name"] == "财务表现")
    assert int(finance.get("rewrite_count") or 0) == 1
    assert finance.get("verification_status") == "supported"
    assert "120.5" in finance.get("markdown", "")
    assert "【待核实】" not in finance.get("markdown", "")


def test_graph_still_pending_after_rewrite():
    retriever = get_retriever("memory")
    _index_sample(retriever)

    def factory(messages, index):
        user_blobs = "\n".join(m.content for m in messages)
        if "章节：财务表现" in user_blobs:
            # Always invent a number that is not in evidence.
            return "营业收入为 888.8 亿元。[synthetic.pdf p4]"
        mapping = {
            "章节：公司概况": ("公司概况", 2),
            "章节：主营业务": ("主营业务", 3),
            "章节：风险因素": ("风险因素", 5),
            "章节：结论": ("结论", 6),
        }
        for key, (name, page) in mapping.items():
            if key in user_blobs:
                return _section_reply(name, page, with_number=None)
        return _section_reply("结论", 6, with_number=None)

    fake = FakeChatModel(reply_factory=factory)
    state = run_report(retriever=retriever, chat_model=fake, doc_ids=["doc-a"], top_k=4)
    finance = next(s for s in state["sections"] if s["name"] == "财务表现")
    assert int(finance.get("rewrite_count") or 0) == 1
    assert finance.get("verification_status") in {"mismatch", "not_found"}
    assert "【待核实】" in finance.get("markdown", "")

def test_graph_rewrite_only_failed_section_six_calls():
    """5 chapters first pass + 1 rewrite of the failing chapter = 6 model calls."""
    retriever = get_retriever("memory")
    _index_sample(retriever)
    finance_writes = {"n": 0}
    preserved = {"overview": None}

    def factory(messages, index):
        user_blobs = "\n".join(m.content for m in messages)
        if "章节：财务表现" in user_blobs:
            finance_writes["n"] += 1
            if finance_writes["n"] <= 1:
                return "营业收入为 999.9 亿元。[synthetic.pdf p4]"
            return "营业收入为 120.5 亿元。[synthetic.pdf p4]"
        if "章节：公司概况" in user_blobs:
            text = _section_reply("公司概况", 2, with_number=None)
            preserved["overview"] = text
            return text
        mapping = {
            "章节：主营业务": ("主营业务", 3),
            "章节：风险因素": ("风险因素", 5),
            "章节：结论": ("结论", 6),
        }
        for key, (name, page) in mapping.items():
            if key in user_blobs:
                return _section_reply(name, page, with_number=None)
        return _section_reply("结论", 6, with_number=None)

    fake = FakeChatModel(reply_factory=factory)
    state = run_report(retriever=retriever, chat_model=fake, doc_ids=["doc-a"], top_k=4)
    assert len(fake.calls) == 6
    assert finance_writes["n"] == 2
    overview = next(s for s in state["sections"] if s["name"] == "公司概况")
    assert preserved["overview"] is not None
    assert preserved["overview"] in overview.get("markdown", "")
    finance = next(s for s in state["sections"] if s["name"] == "财务表现")
    assert int(finance.get("rewrite_count") or 0) == 1
    assert "120.5" in finance.get("markdown", "")



def test_run_summary_counts_pending_and_pages():
    from core.graph.run import build_run_summary

    state = {
        "sections": [
            {
                "name": "财务表现",
                "verification_status": "supported",
                "rewrite_count": 0,
                "markdown": "## 财务表现\n\n营业收入 5 亿元。[a.pdf p7]\n净利润 1 亿元。[a.pdf p7]【待核实】\n",
                "chunks": [{"page": 7}, {"page": 8}],
                "verification_notes": [],
                "elapsed_seconds": 1.23,
            }
        ],
        "export_paths": ["output/x.docx"],
        "errors": [],
    }
    summary = build_run_summary(state, timings={"total_seconds": 1.0}, chunks=3)
    sec = summary["sections"][0]
    assert sec["pending_marks"] == 1 and summary["pending_marks_total"] == 1
    assert sec["cited_pages"] == [7] and sec["retrieved_pages"] == [7, 8]
    assert summary["export_paths"] == ["output/x.docx"]


def test_normalize_section_markdown_keeps_chapter_heading():
    from core.graph.workflow import normalize_section_markdown

    out = normalize_section_markdown("公司概况", "## 公司基本信息与主营定位\n\n正文。\n\n### 1. 小节\n内容")
    lines = out.splitlines()
    assert lines[0] == "## 公司概况"
    assert "### 公司基本信息与主营定位" in lines
    assert "### 1. 小节" in lines
    assert sum(1 for ln in lines if ln.startswith("## ")) == 1
    assert normalize_section_markdown("结论", "## 结论\n\n好。") == "## 结论\n\n好。\n"
    assert normalize_section_markdown("结论", "无标题正文") == "## 结论\n\n无标题正文\n"


def test_sanitize_internal_terms_strips_tool_names():
    from core.graph.workflow import sanitize_internal_terms

    cleaned, warnings = sanitize_internal_terms(
        "写作上下文 calc_financials 给出净利率为5.10%【待核实】。销售净利率约 5%。"
    )
    assert "calc_financials" not in cleaned
    assert "写作上下文" not in cleaned
    assert "销售净利率" not in cleaned
    assert "净利率" in cleaned
    assert warnings


def test_assemble_sanitizes_internal_terms():
    from core.graph.workflow import build_report_graph
    from core.models import Chunk, SearchHit
    from core.qa.llm import ChatMessage

    class _R:
        def index_chunks(self, chunks):
            return None

        def search(self, query, doc_ids=None, top_k=8, mode="hybrid"):
            return [
                SearchHit(
                    chunk_id="c1",
                    doc_id="d",
                    file="a.pdf",
                    text="营业收入 100 元，净利润 10 元。",
                    page=1,
                    section="财务表现",
                    score=1.0,
                )
            ]

    class _C:
        def complete(self, messages: list[ChatMessage]) -> str:
            return (
                "写作上下文 calc_financials 给出净利率为10%（据第1页数据计算）[a.pdf p1]。"
                "销售净利率约 10%。"
            )

    graph = build_report_graph(retriever=_R(), chat_model=_C(), top_k=1)
    state = graph.invoke(
        {
            "template_id": "company_analysis",
            "title": "年报分析",
            "doc_ids": ["d"],
            "sections": [],
            "current_section_index": 0,
            "stage": "plan",
            "report_md": "",
            "export_paths": [],
            "errors": [],
        }
    )
    md = state.get("report_md") or ""
    assert "calc_financials" not in md
    assert "写作上下文" not in md
    assert "销售净利率" not in md
    assert any("assemble:sanitize" in e for e in (state.get("errors") or []))


def test_write_prompt_forbids_internal_terms_and_sales_net_margin():
    from core.graph.workflow import _write_prompt

    messages = _write_prompt(
        {
            "name": "财务表现",
            "questions": ["营业收入如何？"],
            "keywords": ["营业收入"],
            "section_hints": [],
            "chunks": [
                {
                    "chunk_id": "c1",
                    "doc_id": "d",
                    "file": "a.pdf",
                    "text": "营业收入（元）\n100\n80\n净利润（元）\n10\n8",
                    "page": 1,
                    "score": 1.0,
                    "section": "财务指标",
                }
            ],
        }
    )
    system = messages[0].content
    assert "calc_financials" in system  # forbidden word named explicitly in the ban rule
    assert "正文禁止出现 calc_financials" in system
    assert "销售净利率" in system and "不要写成「销售净利率」" in system
    assert "归母净利润口径" in system
    user = messages[1].content
    assert "calc_financials" not in user or "正文不要出现" in user

