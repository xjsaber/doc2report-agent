"""Standalone Streamlit RAG knowledge-base Q&A page (no report graph)."""

from __future__ import annotations

from pathlib import Path
import tempfile

import streamlit as st

from core.index import get_retriever
from core.qa import answer_question, load_dotenv_config
from core.qa.answer import Citation, split_cited_citations
from core.tools.parse_document import ParseDocumentInput, parse_document


def _init_state() -> None:
    if "retriever" not in st.session_state:
        st.session_state.retriever = get_retriever("memory")
    if "documents" not in st.session_state:
        st.session_state.documents = {}  # doc_id -> {file, pages, chunks}


def _ingest_pdf(path: Path) -> str:
    result = parse_document(ParseDocumentInput(file_path=str(path)))
    if not result.ok or result.data is None:
        return result.error or "解析失败"
    data = result.data
    st.session_state.retriever.index_chunks(data.chunks)
    st.session_state.documents[data.doc_id] = {
        "file": path.name,
        "pages": data.pages,
        "chunks": len(data.chunks),
        "sections": [s.title for s in data.sections],
    }
    return f"已入库 {path.name}：{data.pages} 页，{len(data.chunks)} 个片段（doc_id={data.doc_id[:12]}…）"


def _render_citation(citation: Citation, *, cited: bool) -> None:
    tag = "已引用 · " if cited else ""
    with st.expander(f"{tag}{citation.label}  score={citation.score:.4f}"):
        if citation.section:
            st.caption(f"章节：{citation.section} · doc_id={citation.doc_id}")
        else:
            st.caption(f"doc_id={citation.doc_id}")
        st.write(citation.text)


def _render_hits(answer: str | None, citations: list[Citation]) -> None:
    """Cited passages first (marked 已引用), then uncited hits under their own heading."""
    if not citations:
        return
    cited, uncited = split_cited_citations(answer, citations)
    st.subheader("命中原文")
    for citation in cited:
        _render_citation(citation, cited=True)
    if uncited:
        st.caption(f"以下 {len(uncited)} 条为召回但回答未引用的片段")
        for citation in uncited:
            _render_citation(citation, cited=False)


def main() -> None:
    load_dotenv_config()
    st.set_page_config(page_title="doc2report RAG 问答", layout="wide")
    st.title("独立 RAG 知识库问答")
    st.caption("不依赖报告生成流程。上传或选择 PDF → 解析入库 → 混合检索 → 带引用回答。")
    _init_state()

    with st.sidebar:
        st.header("文档入库")
        uploaded = st.file_uploader("上传 PDF（仅公开/自有文档）", type=["pdf"])
        ingest_clicked = st.button("解析并入库", type="primary", disabled=uploaded is None)
        existing = st.text_input("或填写本机已有 PDF 路径")
        path_clicked = st.button("从路径入库", disabled=not existing)
        # Fixed slots: the sidebar keeps the same element layout on every rerun, so
        # Streamlit never shows a stale, semi-transparent copy of 「已入库文档」.
        message_slot = st.empty()
        st.divider()
        st.subheader("已入库文档")
        docs_slot = st.empty()

        if ingest_clicked and uploaded is not None:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(uploaded.getvalue())
                tmp_path = Path(tmp.name)
            try:
                # Preserve display name for citations while parsing the temp bytes.
                display = Path(uploaded.name).name
                target = tmp_path.with_name(display)
                if target != tmp_path:
                    target.write_bytes(tmp_path.read_bytes())
                    tmp_path.unlink(missing_ok=True)
                    tmp_path = target
                st.session_state.ingest_message = _ingest_pdf(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)
        if path_clicked and existing:
            path = Path(existing).expanduser()
            st.session_state.ingest_message = _ingest_pdf(path) if path.is_file() else "文件不存在"

        message = st.session_state.get("ingest_message")
        if message:
            (message_slot.success if message.startswith("已入库") else message_slot.error)(message)
        if not st.session_state.documents:
            docs_slot.write("暂无文档")
        else:
            docs_slot.markdown(
                "\n".join(
                    f"- {meta['file']}（{meta['pages']} 页 / {meta['chunks']} 块）"
                    for meta in st.session_state.documents.values()
                )
            )

    question = st.text_input("提问", placeholder="例如：主营业务是什么？")
    top_k = st.slider("召回条数", min_value=1, max_value=20, value=8)
    if st.button("检索并回答", type="primary") or (question and st.session_state.get("_auto")):
        result = answer_question(
            question,
            retriever=st.session_state.retriever,
            top_k=top_k,
        )
        if result.refused:
            st.warning(result.message or "无法回答")
            st.caption("拒答时不展示被相关性门槛滤掉或未采用的片段，避免误当作「命中原文」。")
        elif result.retrieval_only:
            st.info(result.message or "仅检索结果")
            _render_hits(None, list(result.citations))
        else:
            st.markdown(result.answer or "")
            _render_hits(result.answer, list(result.citations))

if __name__ == "__main__":
    main()
