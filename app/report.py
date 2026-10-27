"""Streamlit report generation page (separate from the RAG Q&A entry)."""

from __future__ import annotations

from pathlib import Path
import tempfile

import streamlit as st

from core.graph.workflow import run_report
from core.index import get_retriever
from core.qa import build_chat_model, load_dotenv_config
from core.tools.export_report import ExportReportInput, export_report
from core.tools.parse_document import ParseDocumentInput, parse_document
from core.tools.templates import ListTemplatesInput, list_templates
from core.qa.answer import parse_citation_markers


def _init_state() -> None:
    st.session_state.setdefault("report_md", "")
    st.session_state.setdefault("report_title", "")
    st.session_state.setdefault("sections", [])
    st.session_state.setdefault("export_md", "")
    st.session_state.setdefault("export_docx", "")
    st.session_state.setdefault("last_doc_id", "")


def _chunk_lookup(sections) -> dict[tuple[str, int], str]:
    lookup: dict[tuple[str, int], str] = {}
    for section in sections or []:
        for hit in section.get("chunks") or []:
            data = hit if isinstance(hit, dict) else hit.model_dump()
            key = (data["file"], int(data["page"]))
            lookup.setdefault(key, data["text"])
    return lookup


def main() -> None:
    load_dotenv_config()
    st.set_page_config(page_title="doc2report 报告生成", layout="wide")
    st.title("年报分析报告生成")
    st.caption("上传 PDF → 选择模板 → LangGraph 五节点生成 → 预览引用 → 下载 Markdown / Word。")
    _init_state()

    templates = list_templates(ListTemplatesInput())
    template_options = (
        {t.template_id: t.title for t in templates.data.templates}
        if templates.ok and templates.data
        else {"company_analysis": "年报分析"}
    )

    with st.sidebar:
        st.header("输入")
        uploaded = st.file_uploader("上传公开年报 PDF", type=["pdf"])
        template_id = st.selectbox(
            "模板",
            options=list(template_options.keys()),
            format_func=lambda key: f"{template_options[key]} ({key})",
        )
        title_override = st.text_input("报告标题（可空）", value="")
        top_k = st.slider("每章召回条数", 1, 12, 6)
        run = st.button("生成报告", type="primary")

    if run:
        if uploaded is None:
            st.error("请先上传 PDF。")
            return
        model = build_chat_model()
        if model is None:
            st.error("未配置 API_KEY。请在项目根目录 .env 中设置后重试（勿提交密钥）。")
            return

        progress = st.progress(0, text="解析 PDF…")
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / Path(uploaded.name).name
            pdf_path.write_bytes(uploaded.getvalue())
            parsed = parse_document(ParseDocumentInput(file_path=str(pdf_path)))
            if not parsed.ok or parsed.data is None:
                st.error(parsed.error or "解析失败")
                return
            progress.progress(20, text=f"已解析 {parsed.data.pages} 页，入库中…")
            retriever = get_retriever("memory")
            retriever.index_chunks(parsed.data.chunks)
            progress.progress(35, text="运行 plan → retrieve → write → verify → assemble…")
            state = run_report(
                retriever=retriever,
                chat_model=model,
                doc_ids=[parsed.data.doc_id],
                template_id=template_id,
                title=title_override or None,
                top_k=top_k,
            )
            progress.progress(85, text="导出 Markdown / Word…")
            report_md = state.get("report_md") or ""
            title = state.get("title") or title_override or template_options.get(template_id, "年报分析")
            out_dir = Path("output")
            md_res = export_report(ExportReportInput(report_md=report_md, format="md", title=title, output_dir=str(out_dir)))
            docx_res = export_report(ExportReportInput(report_md=report_md, format="docx", title=title, output_dir=str(out_dir)))
            progress.progress(100, text="完成")

            st.session_state.report_md = report_md
            st.session_state.report_title = title
            st.session_state.sections = state.get("sections") or []
            st.session_state.export_md = md_res.data.file_path if md_res.ok and md_res.data else ""
            st.session_state.export_docx = docx_res.data.file_path if docx_res.ok and docx_res.data else ""
            st.session_state.last_doc_id = parsed.data.doc_id

            # Per-chapter progress summary
            st.subheader("章节进度")
            for section in st.session_state.sections:
                status = section.get("verification_status")
                rewrites = section.get("rewrite_count")
                st.write(
                    f"- **{section.get('name')}**：核验={status}，重写={rewrites}，"
                    f"耗时={float(section.get('elapsed_seconds') or 0):.1f}s"
                )

    if st.session_state.report_md:
        st.subheader("报告预览")
        st.markdown(st.session_state.report_md)
        lookup = _chunk_lookup(st.session_state.sections)
        markers = parse_citation_markers(st.session_state.report_md)
        if markers:
            st.subheader("引用原文")
            seen: set[tuple[str, int]] = set()
            for file_name, page in markers:
                key = (file_name, page)
                if key in seen:
                    continue
                seen.add(key)
                with st.expander(f"[{file_name} p{page}]"):
                    st.write(lookup.get(key) or "（本章检索片段中未缓存该页原文；请回看对应章节 chunks。）")

        col1, col2 = st.columns(2)
        if st.session_state.export_md and Path(st.session_state.export_md).is_file():
            col1.download_button(
                "下载 Markdown",
                data=Path(st.session_state.export_md).read_bytes(),
                file_name=Path(st.session_state.export_md).name,
                mime="text/markdown",
            )
        if st.session_state.export_docx and Path(st.session_state.export_docx).is_file():
            col2.download_button(
                "下载 Word (.docx)",
                data=Path(st.session_state.export_docx).read_bytes(),
                file_name=Path(st.session_state.export_docx).name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )


if __name__ == "__main__":
    main()
