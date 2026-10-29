"""section_hints prefer in-section hits then fall back globally."""

from core.graph.workflow import build_report_graph
from core.models import Chunk, SearchHit
from core.qa.llm import ChatMessage


class FakeRetriever:
    def __init__(self, hits_by_query_substr: dict[str, list[SearchHit]] | None = None):
        self.calls: list[dict] = []
        self._all = [
            SearchHit(
                chunk_id="toc",
                doc_id="d",
                file="a.pdf",
                text="目录 第一章........1",
                page=1,
                section="目录",
                score=0.99,
            ),
            SearchHit(
                chunk_id="intro",
                doc_id="d",
                file="a.pdf",
                text="公司简介和主要财务指标。本公司注册地深圳，主营物联网。",
                page=5,
                section="公司简介和主要财务指标",
                score=0.80,
            ),
            SearchHit(
                chunk_id="ctrl",
                doc_id="d",
                file="a.pdf",
                text="内部控制与持续经营评估说明。",
                page=90,
                section="内部控制",
                score=0.95,
            ),
        ]

    def index_chunks(self, chunks):
        return None

    def search(self, query, doc_ids=None, top_k=8, mode="hybrid"):
        self.calls.append({"query": query, "top_k": top_k, "mode": mode})
        return list(self._all)[:top_k]


class FakeChat:
    def complete(self, messages: list[ChatMessage]) -> str:
        return "本公司注册地深圳，主营物联网。[a.pdf p5]"


def test_retrieve_prefers_section_hints():
    retriever = FakeRetriever()
    graph = build_report_graph(retriever=retriever, chat_model=FakeChat(), top_k=2)
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
    overview = next(s for s in state["sections"] if s["name"] == "公司概况")
    assert overview.get("section_hints")
    chunk_ids = [
        (h["chunk_id"] if isinstance(h, dict) else h.chunk_id) for h in overview["chunks"]
    ]
    # Hinted intro should beat higher-score TOC/内部控制 when hints match.
    assert "intro" in chunk_ids
    assert retriever.calls and retriever.calls[0]["top_k"] >= 2


def test_company_overview_template_has_company_info_hints():
    from core.tools.templates import LoadTemplateInput, load_template

    loaded = load_template(LoadTemplateInput(template_id="company_analysis"))
    assert loaded.ok and loaded.data
    overview = next(s for s in loaded.data.template.sections if s.name == "公司概况")
    for token in ("公司信息", "注册地址", "股票简称"):
        assert token in overview.keywords
        assert token in overview.section_hints


def test_finance_template_has_balance_sheet_hints():
    from core.tools.templates import LoadTemplateInput, load_template

    loaded = load_template(LoadTemplateInput(template_id="company_analysis"))
    assert loaded.ok and loaded.data
    finance = next(s for s in loaded.data.template.sections if s.name == "财务表现")
    for token in ("资产负债率", "资产总额", "负债总额", "合并资产负债表", "资产总计", "负债合计"):
        assert token in finance.keywords
        assert token in finance.section_hints


def test_retrieve_merges_section_hint_query_hits():
    """r10: long finance query can bury 合并资产负债表; hint-only pass must merge it back."""

    class QueryAwareRetriever:
        def __init__(self):
            self.calls = []

        def index_chunks(self, chunks):
            return None

        def search(self, query, doc_ids=None, top_k=8, mode="hybrid"):
            self.calls.append(query)
            if "合并资产负债表" in query and "营业收入、净利润" not in query:
                return [
                    SearchHit(
                        chunk_id="bs",
                        doc_id="d",
                        file="a.pdf",
                        text="资产总计 100 负债合计 40",
                        page=68,
                        section="1、合并资产负债表",
                        score=0.9,
                    )
                ]
            # Primary question+keyword query: high-score noise only.
            return [
                SearchHit(
                    chunk_id="noise",
                    doc_id="d",
                    file="a.pdf",
                    text="营业收入 1 元",
                    page=13,
                    section="概述",
                    score=0.99,
                )
            ]

    class _C:
        def complete(self, messages):
            return "资产总计 100 元，负债合计 40 元。[a.pdf p68]"

    retriever = QueryAwareRetriever()
    graph = build_report_graph(retriever=retriever, chat_model=_C(), top_k=2)
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
    finance = next(s for s in state["sections"] if s["name"] == "财务表现")
    ids = [(h["chunk_id"] if isinstance(h, dict) else h.chunk_id) for h in finance["chunks"]]
    assert "bs" in ids
    # One primary + one hint supplemental call for 财务表现 (among other sections).
    assert any("合并资产负债表" in q and "营业收入、净利润" not in q for q in retriever.calls)


def test_expand_balance_sheet_neighbor_chunks_pulls_totals():
    from core.graph.workflow import _expand_balance_sheet_neighbor_chunks
    from core.models import Chunk

    class _R:
        def __init__(self):
            self._chunks = {
                "t": Chunk(
                    chunk_id="t",
                    doc_id="d",
                    file="a.pdf",
                    text="1、合并资产负债表 编制单位：X",
                    page=67,
                    section="1、合并资产负债表",
                ),
                "tot": Chunk(
                    chunk_id="tot",
                    doc_id="d",
                    file="a.pdf",
                    text="非流动资产合计 1\n资产总计\n100\n200\n流动负债：\n负债合计\n40\n50",
                    page=68,
                    section="0.00",
                ),
                "noise": Chunk(
                    chunk_id="noise",
                    doc_id="d",
                    file="a.pdf",
                    text="别处的资产总计不应拉入",
                    page=200,
                    section="其他",
                ),
            }

    title = SearchHit(
        chunk_id="t",
        doc_id="d",
        file="a.pdf",
        text="1、合并资产负债表 编制单位：X",
        page=67,
        section="1、合并资产负债表",
        score=0.9,
    )
    out = _expand_balance_sheet_neighbor_chunks([title], retriever=_R(), doc_ids=["d"])
    ids = [h.chunk_id for h in out]
    assert "tot" in ids
    assert "noise" not in ids
