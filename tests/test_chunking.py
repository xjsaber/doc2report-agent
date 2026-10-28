import pytest

from core.models import Chunk
from core.parse import ParsedDocument, ParsedPage, TextBlock, chunk_document, parse_pdf


def make_document(*paragraphs):
    return ParsedDocument(
        doc_id="original", file="synthetic.pdf", engine="pymupdf", tables=[], sections=[],
        pages=[ParsedPage(page=1, text="\n\n".join(paragraphs),
                          blocks=[TextBlock(page=1, text=p) for p in paragraphs])],
    )


def test_chunking(sample_pdf):
    document = parse_pdf(sample_pdf)
    chunks = chunk_document(document)
    assert chunks and all(isinstance(chunk, Chunk) for chunk in chunks)
    assert chunks == chunk_document(document)
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert all(c.doc_id == document.doc_id and c.file == sample_pdf.name for c in chunks)
    assert all(1 <= c.page <= c.page_end <= 3 for c in chunks)
    assert any(c.page == 1 and c.page_end == 2 for c in chunks)
    business = [c for c in chunks if c.section == "第一节 公司概况"]
    assert all(500 <= len(c.text) <= 800 for c in business)
    assert all("第二节" not in c.text for c in business)
    assert chunks[-1].section == "第二节 财务表现"
    assert "Revenue" in chunks[-1].text


def test_paragraph_boundary_overlap_and_no_lost_text():
    paragraphs = [chr(0x4E00 + index) * 300 for index in range(6)]
    document = make_document(*paragraphs)
    chunks = chunk_document(document)
    assert chunks[0].text == paragraphs[0] + "\n\n" + paragraphs[1]
    assert chunks[0].text[-100:] == chunks[1].text[:100]
    reconstructed = chunks[0].text
    for chunk in chunks[1:]:
        overlap = max(size for size in range(1, len(chunk.text)) if reconstructed.endswith(chunk.text[:size]))
        reconstructed += chunk.text[overlap:]
    assert reconstructed == "\n\n".join(paragraphs)


@pytest.mark.parametrize("length", [1, 499, 500, 800, 801, 900, 1500, 2401])
def test_long_paragraph_bounds_overlap_and_full_coverage(length):
    # Unique characters make missing text and accidental reordering detectable.
    text = "".join(chr(0x4E00 + index) for index in range(length))
    chunks = chunk_document(make_document(text))
    assert all(len(c.text) <= 800 for c in chunks)
    assert all(len(c.text) >= min(500, length) for c in chunks)
    covered = set()
    for chunk in chunks:
        start = text.index(chunk.text)
        covered.update(range(start, start + len(chunk.text)))
    assert covered == set(range(length))
    for left, right in zip(chunks, chunks[1:]):
        assert text.index(right.text) <= text.index(left.text) + len(left.text) - 100


def test_sentence_boundary_precedes_hard_split():
    first_sentence = "甲" * 599 + "。"
    chunks = chunk_document(make_document(first_sentence + "乙" * 600))
    assert chunks[0].text == first_sentence


def test_empty_document_has_no_chunks():
    assert chunk_document(make_document("", "  ")) == []


def test_short_sections_are_not_merged_or_overlapped(sample_pdf):
    document = parse_pdf(sample_pdf)
    document.pages = [ParsedPage(page=1, text="", blocks=[
        TextBlock(page=1, text="第一节", is_heading=True), TextBlock(page=1, text="短正文"),
        TextBlock(page=1, text="第二节", is_heading=True), TextBlock(page=1, text="其他正文"),
    ])]
    chunks = chunk_document(document)
    assert [c.text for c in chunks] == ["第一节\n\n短正文", "第二节\n\n其他正文"]


@pytest.mark.parametrize("kwargs", [{"min_chars": 0}, {"overlap": -1}, {"overlap": 500}, {"max_chars": 499}])
def test_invalid_chunk_configuration(kwargs):
    with pytest.raises(ValueError):
        chunk_document(make_document("text"), **kwargs)


def test_toc_pages_dropped_before_chunking():
    from core.parse.chunking import is_toc_page, drop_toc_pages

    toc_lines = "\n".join(f"第{i}章 示例标题........{i}" for i in range(1, 20))
    assert is_toc_page(toc_lines)
    body = "本公司主营物联网读写器与标签产品，报告期内持续拓展海外市场。" * 5
    assert not is_toc_page(body)

    document = ParsedDocument(
        doc_id="toc-doc",
        file="synthetic.pdf",
        engine="pymupdf",
        tables=[],
        sections=[],
        pages=[
            ParsedPage(page=1, text=toc_lines, blocks=[TextBlock(page=1, text=toc_lines)]),
            ParsedPage(
                page=2,
                text=body,
                blocks=[
                    TextBlock(page=2, text="第一节 公司概况", is_heading=True),
                    TextBlock(page=2, text=body),
                ],
            ),
        ],
    )
    filtered = drop_toc_pages(document)
    assert len(filtered.pages) == 1 and filtered.pages[0].page == 2
    chunks = chunk_document(filtered)
    assert chunks
    assert all("........" not in c.text for c in chunks)


def test_title_only_chunk_merges_into_following_body():
    from core.parse.chunking import merge_short_chunks

    title = Chunk(
        chunk_id="t1",
        doc_id="d",
        file="a.pdf",
        text="公司概况",
        page=1,
        section="公司概况",
    )
    body = Chunk(
        chunk_id="t2",
        doc_id="d",
        file="a.pdf",
        text="公司成立于二零一零年，注册地深圳，主营物联网产品与服务。" * 8,
        page=2,
        section="公司概况",
    )
    merged = merge_short_chunks([title, body], min_chars=500)
    assert len(merged) == 1
    assert merged[0].text.startswith("公司概况")
    assert "注册地深圳" in merged[0].text
