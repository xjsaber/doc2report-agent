"""Standalone RAG answer chain with fake chat model (no network)."""

import os

import numpy as np

from core.index import get_retriever
from core.models import Chunk
from core.qa import FakeChatModel, answer_question, load_dotenv_config
from core.qa.answer import REFUSAL_PHRASE
from core.qa.llm import build_chat_model


def _chunk(n: int, text: str, doc_id: str = "a", file: str = "synthetic.pdf", page: int = 2) -> Chunk:
    return Chunk(
        chunk_id=str(n),
        doc_id=doc_id,
        file=file,
        text=text,
        page=page,
        page_end=page,
        section="第一节 公司概况",
    )


def _orthogonal_embedder(query_axis: str = "业务"):
    """Docs about query_axis align with query; others are orthogonal → fail vector gate."""

    def embed(texts):
        rows = []
        for text in texts:
            if query_axis in text:
                rows.append([1.0, 0.0, 0.0])
            else:
                rows.append([0.0, 1.0, 0.0])
        return np.asarray(rows, dtype=np.float32)

    return embed


def test_refuse_when_no_hits():
    retriever = get_retriever("memory")
    result = answer_question("完全不相关的问题XYZ", retriever=retriever, chat_model=FakeChatModel())
    assert result.refused is True
    assert result.answer is None
    assert "依据" in (result.message or "")


def test_answer_with_citations_and_fake_model():
    retriever = get_retriever("memory")
    retriever.index_chunks([
        _chunk(1, "公司主营业务为自主研发的软件产品与技术服务。"),
        _chunk(2, "研发投入持续增加，重点支持核心平台。", "b", "other.pdf", 5),
    ])
    fake = FakeChatModel("主营业务为软件产品与技术服务。[synthetic.pdf p2]")
    result = answer_question("主营业务是什么", retriever=retriever, chat_model=fake, top_k=2)
    assert result.refused is False
    assert result.retrieval_only is False
    assert result.answer and "[synthetic.pdf p2]" in result.answer
    assert result.citations
    assert result.citations[0].file == "synthetic.pdf"
    assert result.citations[0].page == 2
    assert result.citations[0].section == "第一节 公司概况"
    assert fake.calls and fake.calls[0][0].role == "system"


def test_retrieval_only_without_api_key(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    retriever = get_retriever("memory")
    retriever.index_chunks([_chunk(1, "公司主营业务为自主研发的软件产品与技术服务。")])
    result = answer_question("主营业务是什么", retriever=retriever, auto_build_model=True)
    assert result.retrieval_only is True
    assert result.answer is None
    assert result.citations
    assert "API_KEY" in (result.message or "")


def test_build_chat_model_none_without_key(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    assert build_chat_model() is None


def test_empty_question():
    result = answer_question("  ", retriever=get_retriever("memory"), chat_model=FakeChatModel())
    assert result.refused is True


def test_load_dotenv_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("API_KEY=from-file\nMODEL=deepseek-flash\n", encoding="utf-8")
    monkeypatch.setenv("API_KEY", "already-set")
    monkeypatch.delenv("MODEL", raising=False)
    loaded = load_dotenv_config(env)
    assert loaded["API_KEY"] == "from-file"
    assert loaded["MODEL"] == "deepseek-flash"
    assert os.environ["API_KEY"] == "already-set"
    assert os.environ["MODEL"] == "deepseek-flash"


def test_fabricated_citation_refused():
    retriever = get_retriever("memory")
    retriever.index_chunks([_chunk(1, "公司主营业务为自主研发的软件产品与技术服务。")])
    fake = FakeChatModel("主营业务为软件产品。[ghost.pdf p99]")
    result = answer_question("主营业务", retriever=retriever, chat_model=fake)
    assert result.refused is True
    assert result.answer is None
    assert result.citations == []
    assert "不在本次检索" in (result.message or "") or "拒绝" in (result.message or "")
    assert fake.calls  # model was called; post-check refused


def test_missing_citation_refused():
    retriever = get_retriever("memory")
    retriever.index_chunks([_chunk(1, "公司主营业务为自主研发的软件产品与技术服务。")])
    fake = FakeChatModel("主营业务为软件产品，无任何出处。")
    result = answer_question("主营业务", retriever=retriever, chat_model=fake)
    assert result.refused is True
    assert result.answer is None
    assert result.citations == []
    assert "引用" in (result.message or "")


def test_model_self_refusal_phrase():
    # Query overlaps the chunk (passes relevance) but model still emits the fixed refusal phrase.
    retriever = get_retriever("memory")
    retriever.index_chunks([_chunk(1, "公司主营业务为自主研发的软件产品与技术服务。")])
    fake = FakeChatModel(f"{REFUSAL_PHRASE}")
    result = answer_question("主营业务的海外分部收入是多少", retriever=retriever, chat_model=fake)
    assert result.refused is True
    assert result.answer is None
    assert result.message == REFUSAL_PHRASE
    assert result.citations == []
    assert fake.calls


def test_all_irrelevant_skips_model():
    embedder = _orthogonal_embedder("量子力学术语ZXQ")
    retriever = get_retriever("memory", embedder=embedder)
    # Indexed text shares no tokens with the astronomy query and is orthogonal in vector space.
    retriever.index_chunks([_chunk(1, "公司办公地址与联系电话已披露。")])
    fake = FakeChatModel("不应被调用")
    result = answer_question(
        "量子力学术语ZXQ黑洞熵是多少",
        retriever=retriever,
        chat_model=fake,
        min_vector_score=0.35,
    )
    assert result.refused is True
    assert result.answer is None
    assert "依据" in (result.message or "")
    assert fake.calls == []

def test_refuse_question_absent_from_report():
    """Boilerplate tokens like 公司/年度/报告 must not keep irrelevant hits alive."""
    embedder = _orthogonal_embedder("火星移民ZXQ")
    retriever = get_retriever("memory", embedder=embedder)
    retriever.index_chunks(
        [
            _chunk(1, "本公司年度报告披露公司董事会与治理结构相关情况。"),
            _chunk(2, "本公司年度报告说明公司股东大会召开情况。", page=3),
            _chunk(3, "本公司年度报告列示公司董事简历与任职情况。", page=4),
        ]
    )
    fake = FakeChatModel("不应被调用")
    result = answer_question(
        "火星移民ZXQ计划的预算是多少",
        retriever=retriever,
        chat_model=fake,
        min_vector_score=0.35,
    )
    assert result.refused is True
    assert result.answer is None
    assert "依据" in (result.message or "")
    assert fake.calls == []



def test_split_cited_citations_orders_cited_first():
    from core.qa.answer import Citation, split_cited_citations

    hits = [
        Citation(file="a.pdf", page=19, chunk_id="c19", text="x", score=0.9, doc_id="d"),
        Citation(file="a.pdf", page=89, chunk_id="c89", text="y", score=0.8, doc_id="d"),
        Citation(file="a.pdf", page=28, chunk_id="c28", text="z", score=0.7, doc_id="d"),
    ]
    cited, uncited = split_cited_citations("主营 RFID。[a.pdf p89] 产品线。[a.pdf p28]", hits)
    assert [c.page for c in cited] == [89, 28]
    assert [c.page for c in uncited] == [19]
    assert split_cited_citations(None, hits) == ([], hits)
