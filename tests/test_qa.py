"""Standalone RAG answer chain with fake chat model (no network)."""

import os

from core.index import get_retriever
from core.models import Chunk
from core.qa import FakeChatModel, answer_question, load_dotenv_config
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


def test_appends_missing_citation_markers():
    retriever = get_retriever("memory")
    retriever.index_chunks([_chunk(1, "公司主营业务为自主研发的软件产品与技术服务。")])
    fake = FakeChatModel("主营业务为软件产品。")
    result = answer_question("主营业务", retriever=retriever, chat_model=fake)
    assert result.answer and "[synthetic.pdf p2]" in result.answer
