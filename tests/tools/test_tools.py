"""Positive/error case slots; no simulated business success."""
import pytest

from core.tools.parse_document import ParseDocumentInput, parse_document


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


@pytest.mark.parametrize("tool", [
    "get_table", "calc_financials",
    "verify_claim", "render_section", "export_report", "list_templates", "load_template",
])
@pytest.mark.parametrize("case", ["success", "error"])
@pytest.mark.skip(reason="Step 1: business implementation deferred")
def test_tool_behavior(tool, case):
    pass
