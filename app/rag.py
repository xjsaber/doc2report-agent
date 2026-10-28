"""Standalone Streamlit RAG knowledge-base Q&A page (no report graph)."""

from __future__ import annotations

from pathlib import Path
import tempfile

import streamlit as st

from core.index import get_retriever
from core.qa import answer_question, load_dotenv_config
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


def main() -> None:
    load_dotenv_config()
    st.set_page_config(page_title="doc2report RAG 问答", layout="wide")
    st.title("独立 RAG 知识库问答")
    st.caption("不依赖报告生成流程。上传或选择 PDF → 解析入库 → 混合检索 → 带引用回答。")
    _init_state()

    with st.sidebar:
        st.header("文档入库")
        uploaded = st.file_uploader("上传 PDF（仅公开/自有文档）", type=["pdf"])
        if uploaded is not None and st.button("解析并入库", type="primary"):
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
                message = _ingest_pdf(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)
            st.success(message) if message.startswith("已入库") else st.error(message)

        existing = st.text_input("或填写本机已有 PDF 路径")
        if existing and st.button("从路径入库"):
            path = Path(existing).expanduser()
            if not path.is_file():
                st.error("文件不存在")
            else:
                message = _ingest_pdf(path)
                st.success(message) if message.startswith("已入库") else st.error(message)

        st.divider()
        st.subheader("已入库文档")
        if not st.session_state.documents:
            st.write("暂无文档")
        else:
            for doc_id, meta in st.session_state.documents.items():
                st.write(f"- {meta['file']}（{meta['pages']} 页 / {meta['chunks']} 块）")

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
            if result.citations:
                st.subheader("命中原文")
                for citation in result.citations:
                    with st.expander(f"{citation.label}  score={citation.score:.4f}"):
                        if citation.section:
                            st.caption(f"章节：{citation.section} · doc_id={citation.doc_id}")
                        else:
                            st.caption(f"doc_id={citation.doc_id}")
                        st.write(citation.text)
        else:
            st.markdown(result.answer or "")
            if result.citations:
                st.subheader("命中原文")
                for citation in result.citations:
                    with st.expander(f"{citation.label}  score={citation.score:.4f}"):
                        if citation.section:
                            st.caption(f"章节：{citation.section} · doc_id={citation.doc_id}")
                        else:
                            st.caption(f"doc_id={citation.doc_id}")
                        st.write(citation.text)


if __name__ == "__main__":
    main()
