import logging
import sys
from types import ModuleType, SimpleNamespace

import pymupdf
import pytest

from core.parse import parse_pdf


def test_pdf_preserves_pages_headings_tables_and_identity(sample_pdf):
    document = parse_pdf(sample_pdf)
    assert document.file == sample_pdf.name
    assert document.engine == "pymupdf"
    assert [page.page for page in document.pages] == [1, 2, 3]
    assert "公司业务段落0" in document.pages[0].text
    assert "公司业务段落2" in document.pages[1].text
    assert [(s.title, s.page_start, s.page_end) for s in document.sections] == [
        ("第一节 公司概况", 1, 2), ("第二节 财务表现", 3, 3),
    ]
    table = document.tables[0]
    assert table.page == 3
    assert table.headers == ["Metric", "Value"]
    assert table.rows == [["Revenue", "120"], ["Profit", "30"]]
    assert "Revenue" in table.raw_text
    assert table.caption == "Financial summary"
    assert parse_pdf(sample_pdf).doc_id == document.doc_id
    copy = sample_pdf.with_name("copy.pdf")
    copy.write_bytes(sample_pdf.read_bytes())
    assert parse_pdf(copy).doc_id == document.doc_id


def test_missing_mineru_falls_back_and_logs(sample_pdf, monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "mineru", None)
    monkeypatch.setitem(sys.modules, "mineru.parser", None)
    with caplog.at_level(logging.WARNING):
        document = parse_pdf(sample_pdf, engine="mineru")
    assert document.engine == "pymupdf"
    assert len(document.pages) == 3
    assert "MinerU is not installed" in caplog.text
    assert "falling back to PyMuPDF" in caplog.text


def test_mineru_adapter_preserves_original_page_indices(sample_pdf, monkeypatch):
    parser = ModuleType("mineru.parser")
    renderer = ModuleType("mineru.render")
    calls = []

    def fake_parse(path, **kwargs):
        calls.append((path, kwargs))
        return SimpleNamespace(middle_json={})

    parser.parse = fake_parse
    renderer.RenderFormat = SimpleNamespace(CONTENT_LIST="content_list")
    renderer.render = lambda *_: [
        {"type": "text", "text": "第一节 公司概况", "text_level": 1, "page_idx": 0},
        {"type": "text", "text": "业务原文", "page_idx": 1},
        {"type": "table", "table_body": "<table><tr><td>120</td></tr></table>", "page_idx": 2},
    ]
    monkeypatch.setitem(sys.modules, "mineru.parser", parser)
    monkeypatch.setitem(sys.modules, "mineru.render", renderer)
    document = parse_pdf(sample_pdf, engine="mineru")
    assert document.engine == "mineru"
    assert document.pages[1].blocks[0].page == 2
    assert document.tables[0].page == 3
    assert "120" in document.tables[0].raw_text
    assert calls == [(str(sample_pdf), {"tier": "flash", "ocr_mode": "txt"})]


def test_failed_mineru_falls_back(sample_pdf, monkeypatch, caplog):
    def fail(*_):
        raise RuntimeError("broken optional runtime")

    monkeypatch.setattr("core.parse.pdf._mineru_document", fail)
    with caplog.at_level(logging.WARNING):
        assert parse_pdf(sample_pdf, engine="mineru").engine == "pymupdf"
    assert "MinerU failed" in caplog.text


def test_table_failure_keeps_page_text(sample_pdf, monkeypatch, caplog):
    def fail(*_):
        raise RuntimeError("table detector failed")

    monkeypatch.setattr(pymupdf.Page, "find_tables", fail)
    with caplog.at_level(logging.WARNING):
        document = parse_pdf(sample_pdf)
    assert document.tables == []
    assert "Revenue" in document.pages[2].text
    assert "keeping raw text" in caplog.text


def test_blank_pdf_keeps_physical_page_and_logs(tmp_path, caplog):
    path = tmp_path / "blank.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(path)
    with caplog.at_level(logging.WARNING):
        document = parse_pdf(path)
    assert len(document.pages) == 1
    assert document.pages[0].text == ""
    assert "OCR is not enabled" in caplog.text


@pytest.mark.parametrize("case", ["missing", "invalid", "wrong_extension", "encrypted", "unsupported_engine"])
def test_invalid_pdf_inputs(tmp_path, case):
    path = tmp_path / "bad.pdf"
    if case == "invalid":
        path.write_bytes(b"This is not a PDF")
    elif case == "wrong_extension":
        path = path.with_suffix(".txt")
        path.write_text("text")
    elif case == "encrypted":
        with pymupdf.open() as pdf:
            pdf.new_page()
            pdf.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader")
    with pytest.raises((ValueError, OSError, RuntimeError)):
        parse_pdf(path, engine="unknown" if case == "unsupported_engine" else "pymupdf")
