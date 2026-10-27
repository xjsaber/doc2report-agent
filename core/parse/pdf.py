"""Local PyMuPDF extraction and an optional MinerU 4 adapter."""

from collections import Counter
from hashlib import sha256
import logging
from pathlib import Path
import re
from typing import Literal

import pymupdf

from core.parse.models import (
    ParsedDocument, ParsedPage, ParsedTable, TextBlock, collect_sections,
)

logger = logging.getLogger(__name__)
_HEADING = re.compile(
    r"^(?:第[一二三四五六七八九十百零〇\d]+[章节篇部]|"
    r"[一二三四五六七八九十]+[、．.]|\d+(?:\.\d+)*[、．.\s]\s*\S)"
)


def _page_blocks(page: pymupdf.Page) -> list[TextBlock]:
    layout = page.get_text("dict", sort=True, flags=pymupdf.TEXTFLAGS_TEXT)
    font_weights: Counter[float] = Counter()
    for block in layout["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                font_weights[round(span["size"], 1)] += len(span["text"].strip())
    body_size = font_weights.most_common(1)[0][0] if font_weights else 11
    result: list[TextBlock] = []
    for block in layout["blocks"]:
        paragraph: list[str] = []
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue
            size = max(span["size"] for span in line["spans"])
            heading = len(text) <= 80 and not text.endswith(("。", "；", ";")) and (
                bool(_HEADING.match(text)) or size >= body_size * 1.2
            )
            if heading:
                if paragraph:
                    result.append(TextBlock(text="\n".join(paragraph), page=page.number + 1))
                    paragraph = []
                result.append(TextBlock(text=text, page=page.number + 1, is_heading=True))
            else:
                paragraph.append(text)
        if paragraph:
            result.append(TextBlock(text="\n".join(paragraph), page=page.number + 1))
    return result


def _page_tables(page: pymupdf.Page, doc_id: str) -> list[ParsedTable]:
    tables: list[ParsedTable] = []
    try:
        found = page.find_tables()
    except Exception as exc:
        # Table detection must never discard the page's already extracted text.
        logger.warning("Table detection failed on page %s; keeping raw text: %s", page.number + 1, exc)
        return tables
    for index, table in enumerate(found.tables):
        try:
            grid = [[cell or "" for cell in row] for row in table.extract()]
            if not grid:
                continue
            preceding = [
                block for block in page.get_text("blocks", sort=True)
                if block[3] <= table.bbox[1] and block[6] == 0 and block[4].strip()
            ]
            caption = max(preceding, key=lambda block: block[3])[4].strip() if preceding else None
            headers = [name or "" for name in table.header.names]
            tables.append(ParsedTable(
                table_id=f"{doc_id}:p{page.number + 1}:t{index + 1}",
                page=page.number + 1, caption=caption,
                headers=headers, rows=grid if table.header.external else grid[1:],
                raw_text=page.get_textbox(table.bbox).strip(),
            ))
        except Exception as exc:
            logger.warning("Table extraction failed on page %s; keeping raw text: %s", page.number + 1, exc)
    return tables


def _pymupdf_document(pdf: pymupdf.Document, path: Path, doc_id: str) -> ParsedDocument:
    pages: list[ParsedPage] = []
    tables: list[ParsedTable] = []
    for page in pdf:
        blocks = _page_blocks(page)
        margin_lines = []
        for block in page.get_text("dict", sort=True, flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
            for line in block.get("lines", []):
                if line["bbox"][3] <= page.rect.height * 0.10 or line["bbox"][1] >= page.rect.height * 0.90:
                    margin_lines.append("".join(span["text"] for span in line["spans"]).strip())
        pages.append(ParsedPage(page=page.number + 1, text=page.get_text(sort=True),
                                blocks=blocks, margin_lines=margin_lines))
        tables.extend(_page_tables(page, doc_id))
    if not any(page.text.strip() for page in pages):
        logger.warning("PDF has no extractable text; OCR is not enabled: %s", path.name)
    return ParsedDocument(
        doc_id=doc_id, file=path.name, engine="pymupdf", pages=pages,
        sections=collect_sections(pages), tables=tables,
    )


def _mineru_document(path: Path, doc_id: str, page_count: int) -> ParsedDocument:
    # Use MinerU 4's local SDK in Flash/txt mode rather than its HTTP client.
    # Imports are lazy so the default parser never requires MinerU.
    from mineru.parser import parse
    from mineru.render import RenderFormat, render

    result = parse(str(path), tier="flash", ocr_mode="txt")
    content = render(result.middle_json, RenderFormat.CONTENT_LIST)
    blocks: dict[int, list[TextBlock]] = {number: [] for number in range(1, page_count + 1)}
    tables: list[ParsedTable] = []
    for item in content:
        number = int(item["page_idx"]) + 1
        if number not in blocks:
            raise ValueError("MinerU returned a page outside the PDF")
        if item["type"] == "text":
            text = item["text"].strip()
            if text:
                blocks[number].append(TextBlock(
                    page=number, text=text, is_heading=bool(item.get("text_level", 0)),
                ))
        elif item["type"] == "table":
            # Preserve table markup when no reliable cell grid is available.
            raw = item.get("table_body", "").strip()
            caption = " ".join(item.get("table_caption", [])) or None
            tables.append(ParsedTable(
                table_id=f"{doc_id}:p{number}:t{len(tables) + 1}", page=number,
                caption=caption, headers=[], rows=[], raw_text=raw,
            ))
            if raw:
                blocks[number].append(TextBlock(page=number, text=raw))
    if not any(blocks.values()):
        raise ValueError("MinerU returned no text")
    pages = [ParsedPage(page=number, text="\n\n".join(b.text for b in entries), blocks=entries)
             for number, entries in blocks.items()]
    return ParsedDocument(
        doc_id=doc_id, file=path.name, engine="mineru", pages=pages,
        sections=collect_sections(pages), tables=tables,
    )


def parse_pdf(file_path: str | Path, engine: Literal["pymupdf", "mineru"] = "pymupdf") -> ParsedDocument:
    """Parse a local PDF; unavailable or failed MinerU falls back with a warning."""
    if engine not in ("pymupdf", "mineru"):
        raise ValueError(f"Unsupported parser engine: {engine}")
    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("Only local PDF files are supported")
    content = path.read_bytes()
    doc_id = sha256(content).hexdigest()
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        if pdf.needs_pass:
            raise ValueError("Encrypted PDFs requiring a password are not supported")
        if not pdf.page_count:
            raise ValueError("PDF has no pages")
        if engine == "mineru":
            try:
                return _mineru_document(path, doc_id, pdf.page_count)
            except ImportError as exc:
                logger.warning("MinerU is not installed or its API is unavailable; falling back to PyMuPDF: %s", exc)
            except Exception as exc:
                logger.warning("MinerU failed; falling back to PyMuPDF: %s", exc)
        return _pymupdf_document(pdf, path, doc_id)
