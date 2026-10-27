from pathlib import Path
"""Positive/error cases for v1 tools including export_report."""

from decimal import Decimal

import pytest

from core.models import Fact, Source
from core.parse.store import clear_documents, put_document
from core.tools.calc_financials import CalcFinancialsInput, MetricValue, PeriodValues, calc_financials
from core.tools.export_report import ExportReportInput, export_report
from core.tools.get_table import GetTableInput, get_table
from core.tools.parse_document import ParseDocumentInput, parse_document
from core.tools.render_section import RenderSectionInput, render_section
from core.tools.templates import ListTemplatesInput, LoadTemplateInput, list_templates, load_template
from core.tools.verify_claim import VerifyClaimInput, verify_claim
from core.parse.models import ParsedDocument, ParsedPage, ParsedTable


def test_parse_document_success(sample_pdf, caplog):
    with caplog.at_level("INFO"):
        result = parse_document(ParseDocumentInput(file_path=str(sample_pdf)))
    assert result.ok is True
    assert result.error is None
    assert result.data.pages == 3
    assert result.data.engine == "pymupdf"
    assert result.data.sections[0].title == "第一节 公司概况"
    assert result.data.tables[0].page == 3
    assert result.data.chunks
    assert {s.chunk_id for s in result.sources} == {c.chunk_id for c in result.data.chunks}
    assert "tool=parse_document" in caplog.text
    assert "elapsed_seconds=" in caplog.text
    assert "ok=True" in caplog.text


@pytest.mark.parametrize("case", ["missing", "invalid", "directory", "wrong_extension"])
def test_parse_document_error(tmp_path, caplog, case):
    path = tmp_path / "invalid.pdf"
    if case == "invalid":
        path.write_bytes(b"invalid PDF")
    elif case == "directory":
        path.mkdir()
    elif case == "wrong_extension":
        path = path.with_suffix(".txt")
        path.write_text("original text")
    with caplog.at_level("INFO"):
        result = parse_document(ParseDocumentInput(file_path=str(path)))
    assert result.ok is False
    assert result.data is None
    assert result.error
    assert result.sources == []
    assert "ok=False" in caplog.text


def test_parse_document_mineru_fallback(sample_pdf, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "mineru.parser", None)
    result = parse_document(ParseDocumentInput(file_path=str(sample_pdf), engine="mineru"))
    assert result.ok
    assert result.data.engine == "pymupdf"


def _seed_table_doc(doc_id: str = "doc-table") -> ParsedDocument:
    clear_documents()
    document = ParsedDocument(
        doc_id=doc_id,
        file="synthetic.pdf",
        engine="pymupdf",
        pages=[
            ParsedPage(page=1, text="合并利润表及相关说明", blocks=[]),
            ParsedPage(page=2, text="其他页面", blocks=[]),
        ],
        sections=[],
        tables=[
            ParsedTable(
                table_id="t1",
                page=1,
                caption="合并利润表",
                headers=["项目", "本期"],
                rows=[["营业收入", "100"], ["净利润", "20"]],
                raw_text="合并利润表 营业收入 100 净利润 20",
            )
        ],
    )
    put_document(document)
    return document


def test_get_table_success_by_id():
    _seed_table_doc()
    result = get_table(GetTableInput(doc_id="doc-table", table_id="t1"))
    assert result.ok and result.data
    assert result.data.headers[0] == "项目"
    assert result.data.page == 1


def test_get_table_success_by_keyword():
    _seed_table_doc()
    result = get_table(GetTableInput(doc_id="doc-table", keyword="合并利润表"))
    assert result.ok and result.data
    assert result.data.table_id == "t1"


def test_get_table_error_missing_doc():
    clear_documents()
    result = get_table(GetTableInput(doc_id="missing", table_id="t1"))
    assert result.ok is False
    assert result.error


def test_calc_financials_success():
    src = [Source(file="synthetic.pdf", page=1, chunk_id="c1")]
    result = calc_financials(
        CalcFinancialsInput(
            values={
                "营业收入": PeriodValues(
                    current=MetricValue(value=Decimal("120"), sources=src),
                    previous=MetricValue(value=Decimal("100"), sources=src),
                ),
                "营业成本": PeriodValues(current=MetricValue(value=Decimal("60"), sources=src)),
                "净利润": PeriodValues(
                    current=MetricValue(value=Decimal("30"), sources=src),
                    previous=MetricValue(value=Decimal("20"), sources=src),
                ),
                "经营活动现金流": PeriodValues(current=MetricValue(value=Decimal("15"), sources=src)),
                "总资产": PeriodValues(current=MetricValue(value=Decimal("200"), sources=src)),
                "总负债": PeriodValues(current=MetricValue(value=Decimal("80"), sources=src)),
            }
        )
    )
    assert result.ok and result.data
    by_name = {m.name: m for m in result.data.metrics}
    assert by_name["营业收入同比增速"].value == Decimal("0.2")
    assert by_name["毛利率"].value == Decimal("0.5")
    assert by_name["净利率"].value == Decimal("0.25")
    assert by_name["资产负债率"].value == Decimal("0.4")
    assert by_name["净现比"].value == Decimal("0.5")


def test_calc_financials_error_empty():
    result = calc_financials(CalcFinancialsInput(values={}))
    assert result.ok is False


def test_verify_claim_success_and_mismatch():
    lookup = {"c1": "营业收入 120.5 亿元，净利润 30 亿元。"}
    ok = verify_claim(VerifyClaimInput(claim="营业收入为 120.5 亿元", source_chunk_ids=["c1"]), chunk_lookup=lookup)
    assert ok.ok and ok.data and ok.data.status == "supported"
    bad = verify_claim(VerifyClaimInput(claim="营业收入为 999 亿元", source_chunk_ids=["c1"]), chunk_lookup=lookup)
    assert bad.ok and bad.data and bad.data.status == "mismatch"


def test_verify_claim_error_without_lookup():
    result = verify_claim(VerifyClaimInput(claim="营收 1", source_chunk_ids=["c1"]))
    assert result.ok is False


def test_render_section_success():
    result = render_section(
        RenderSectionInput(
            section_name="公司概况",
            template_id="company_analysis",
            facts=[
                Fact(
                    text="公司专注软件产品。",
                    sources=[Source(file="synthetic.pdf", page=2, chunk_id="c1")],
                )
            ],
        )
    )
    assert result.ok and result.data
    assert "## 公司概况" in result.data.markdown
    assert "[synthetic.pdf p2]" in result.data.markdown


def test_render_section_error_empty_facts():
    result = render_section(
        RenderSectionInput(section_name="公司概况", template_id="company_analysis", facts=[])
    )
    assert result.ok is False


def test_list_templates_success():
    result = list_templates(ListTemplatesInput())
    assert result.ok and result.data
    assert any(t.template_id == "company_analysis" for t in result.data.templates)


def test_load_template_success_and_error():
    ok = load_template(LoadTemplateInput(template_id="company_analysis"))
    assert ok.ok and ok.data and ok.data.template.title == "年报分析"
    bad = load_template(LoadTemplateInput(template_id="does-not-exist"))
    assert bad.ok is False


def test_export_report_md_and_docx_structure(tmp_path):
    report_md = """# 年报分析

## 公司概况

公司专注软件产品与技术服务。[synthetic.pdf p2]

## 财务表现

营业收入为 120.5 亿元。[synthetic.pdf p4]【待核实】
"""
    md = export_report(
        ExportReportInput(report_md=report_md, format="md", title="年报分析", output_dir=str(tmp_path))
    )
    assert md.ok and md.data
    md_path = Path(md.data.file_path)
    assert md_path.is_file()
    assert "公司概况" in md_path.read_text(encoding="utf-8")

    docx_res = export_report(
        ExportReportInput(report_md=report_md, format="docx", title="年报分析", output_dir=str(tmp_path))
    )
    assert docx_res.ok and docx_res.data
    docx_path = Path(docx_res.data.file_path)
    assert docx_path.is_file()

    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    document = Document(str(docx_path))
    texts = [p.text for p in document.paragraphs]
    joined = "\n".join(texts)
    assert "年报分析" in joined
    assert "公司概况" in joined
    assert "财务表现" in joined
    assert "目录" in joined
    assert "[synthetic.pdf p2]" in joined or "synthetic.pdf" in joined
    # Heading count: title + 目录 + 2 sections + 全部引用 >= 4
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert len(headings) >= 3
    highlighted = False
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            if "待核实" in run.text and run.font.highlight_color == WD_COLOR_INDEX.YELLOW:
                highlighted = True
    assert highlighted is True


def test_export_report_error_empty(tmp_path):
    result = export_report(
        ExportReportInput(report_md="   ", format="md", title="空", output_dir=str(tmp_path))
    )
    assert result.ok is False
    assert result.error
