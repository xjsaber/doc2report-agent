from core.parse.models import ParsedDocument, ParsedPage, TextBlock
from core.parse.denoise import remove_repeated_margins
from core.parse.chunking import chunk_document
from core.parse.pdf import parse_pdf
import pymupdf


def document(headers):
    return ParsedDocument(doc_id="synthetic", file="synthetic.pdf", engine="synthetic",
        sections=[], tables=[], pages=[ParsedPage(page=i, text="", blocks=[
            TextBlock(page=i, text=f"{header}\n正文 {i}\n年度报告\n正文结束 {i}\n第 {i} 页")
        ]) for i, header in enumerate(headers, 1)])


def test_threshold_body_and_original():
    original = document(["年度报告"] * 3 + [f"唯一标题 {i}" for i in range(7)])
    clean = remove_repeated_margins(original)
    assert clean.pages[0].text.startswith("正文 1")
    assert "年度报告" in clean.pages[0].text  # interior occurrence retained
    assert "第 1 页" not in clean.pages[0].text
    assert "第 1 页" in original.pages[0].blocks[0].text
    assert clean.pages[3].text.startswith("唯一标题 0")
    below = remove_repeated_margins(document(["年度报告"] * 2 + [f"唯一 {i}" for i in range(8)]))
    assert below.pages[0].text.startswith("年度报告")
    assert remove_repeated_margins(document(["年度报告"])).pages[0].text.startswith("年度报告")


def test_pdf_pipeline(tmp_path):
    path = tmp_path / "margins.pdf"
    with pymupdf.open() as pdf:
        for i in range(4):
            page = pdf.new_page()
            page.insert_text((50, 30), "Synthetic annual report")
            page.insert_text((50, 200), f"Unique body {i}")
            page.insert_text((50, 810), str(i + 1))
        pdf.save(path)
    parsed = parse_pdf(path)
    chunks = chunk_document(parsed)
    assert "Synthetic annual report" not in "".join(c.text for c in chunks)
    assert all(f"Unique body {i}" in "".join(c.text for c in chunks) for i in range(4))
    assert parsed.pages[0].text.startswith("Synthetic annual report")
