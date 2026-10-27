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
