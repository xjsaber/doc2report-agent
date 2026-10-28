"""Audit-report boilerplate must not become risk / conclusion material (r8 finish-report)."""

from core.graph.audit_filter import (
    AUDIT_PROMPT_RULE,
    demote_audit_boilerplate,
    is_audit_boilerplate,
    section_needs_audit_filter,
)
from core.graph.workflow import _write_prompt

GOING_CONCERN = (
    "我们的结论基于截至审计报告日可获得的信息。然而，未来的事项或情况可能导致某公司不能持续经营。"
    "（5）评价财务报表的总体列报、结构和内容，并评价财务报表是否公允反映相关交易和事项。"
)
RESPONSIBILITY = (
    "我们的目标是对财务报表整体是否不存在由于舞弊或错误导致的重大错报获取合理保证，"
    "并出具包含审计意见的审计报告。"
)
REAL_RISK = "公司面临市场竞争加剧的风险，若不能持续推出新产品，可能导致收入下滑。"
KAM = "由于营业收入是合并利润表的重要组成部分，可能存在不恰当收入确认的固有风险。因此我们将营业收入的确认作为关键审计事项。"


def _hit(text, section, chunk_id):
    return {"text": text, "section": section, "chunk_id": chunk_id, "file": "a.pdf", "page": 1, "score": 1.0, "doc_id": "d"}


def test_detects_auditor_standard_paragraphs():
    assert is_audit_boilerplate(GOING_CONCERN, "六、注册会计师对财务报表审计的责任")
    assert is_audit_boilerplate(GOING_CONCERN, None)  # phrase-based even without section title
    assert is_audit_boilerplate(RESPONSIBILITY, "")
    assert is_audit_boilerplate("我们审计了后附的财务报表。", "一、审计意见")


def test_keeps_company_specific_text():
    assert not is_audit_boilerplate(REAL_RISK, "十一、公司未来发展的展望")
    assert not is_audit_boilerplate(KAM, "1、事项描述")
    assert not is_audit_boilerplate("经评估，本公司持续经营能力良好。", "2、持续经营")


def test_demote_excludes_boilerplate_but_never_empties():
    hits = [_hit(GOING_CONCERN, "六、注册会计师对财务报表审计的责任", "a"), _hit(REAL_RISK, "可能面对的风险", "b")]
    assert [h["chunk_id"] for h in demote_audit_boilerplate(hits)] == ["b"]
    only = [_hit(GOING_CONCERN, "六、注册会计师对财务报表审计的责任", "a")]
    assert demote_audit_boilerplate(only) == only


def test_only_risk_and_conclusion_sections_filtered():
    assert section_needs_audit_filter("风险因素")
    assert section_needs_audit_filter("结论")
    assert not section_needs_audit_filter("财务表现")


def test_risk_prompt_forbids_audit_wording():
    section = {"name": "风险因素", "questions": ["主要风险？"], "keywords": [], "chunks": [_hit(REAL_RISK, "风险", "b")]}
    system = _write_prompt(section)[0].content
    assert AUDIT_PROMPT_RULE in system
    other = {"name": "财务表现", "questions": ["收入？"], "keywords": [], "chunks": [_hit(REAL_RISK, "风险", "b")]}
    assert AUDIT_PROMPT_RULE not in _write_prompt(other)[0].content


def test_graph_risk_section_excludes_audit_boilerplate():
    from core.graph.workflow import build_report_graph
    from core.models import SearchHit

    class Retriever:
        def index_chunks(self, chunks):
            return None

        def search(self, query, doc_ids=None, top_k=8, mode="hybrid"):
            return [
                SearchHit(chunk_id="audit", doc_id="d", file="a.pdf", text=GOING_CONCERN, page=65,
                          section="六、注册会计师对财务报表审计的责任", score=0.99),
                SearchHit(chunk_id="risk", doc_id="d", file="a.pdf", text=REAL_RISK, page=30,
                          section="可能面对的风险", score=0.50),
            ][:top_k]

    class Chat:
        def complete(self, messages):
            return "公司面临市场竞争加剧的风险。[a.pdf p30]"

    state = build_report_graph(retriever=Retriever(), chat_model=Chat(), top_k=2).invoke(
        {"template_id": "company_analysis", "title": "t", "doc_ids": ["d"], "sections": [],
         "current_section_index": 0, "stage": "plan", "report_md": "", "export_paths": [], "errors": []}
    )
    by_name = {s["name"]: [(h["chunk_id"] if isinstance(h, dict) else h.chunk_id) for h in s["chunks"]]
               for s in state["sections"]}
    assert "audit" not in by_name["风险因素"]
    assert "audit" not in by_name["结论"]
    assert "audit" in by_name["财务表现"]  # other chapters unchanged
