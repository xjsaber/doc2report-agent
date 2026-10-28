"""Heading-aware character chunks with paragraph boundaries and overlap."""

from bisect import bisect_left, bisect_right
from hashlib import sha256
import re

from core.models import Chunk
from core.parse.models import ParsedDocument, TextBlock
from core.parse.denoise import remove_repeated_margins

# Dot leaders or trailing page numbers typical of 目录 pages.
_TOC_LEADER_RE = re.compile(r"[·\.．…─\-_]{2,}\s*\d+\s*$")
_TOC_TRAIL_PAGE_RE = re.compile(r".+\s{2,}\d{1,4}\s*$")


def is_toc_page(page_text: str, *, min_lines: int = 6, ratio: float = 0.4) -> bool:
    """Heuristic: many lines look like TOC entries (dot leaders / trailing page nums)."""
    lines = [ln.strip() for ln in (page_text or "").splitlines() if ln.strip()]
    if len(lines) < min_lines:
        return False
    toc_like = 0
    for line in lines:
        if _TOC_LEADER_RE.search(line) or _TOC_TRAIL_PAGE_RE.match(line):
            toc_like += 1
    return (toc_like / len(lines)) >= ratio


def drop_toc_pages(document: ParsedDocument) -> ParsedDocument:
    """Return a copy of the document without directory/TOC pages."""
    kept = [page for page in document.pages if not is_toc_page(page.text)]
    if len(kept) == len(document.pages):
        return document
    return document.model_copy(update={"pages": kept})


def _is_title_only(chunk: Chunk, *, body_min: int = 1) -> bool:
    """True when the chunk is essentially only a heading (no meaningful body prose).

    Short bodies that still contain prose stay as their own chunk; pass-2 same-section
    merge continues to handle adjacent under-length chunks.
    """
    text = (chunk.text or "").strip()
    if not text:
        return True
    section = (chunk.section or "").strip()
    compact = text.replace("\n", "").replace(" ", "")
    if section and compact == section.replace(" ", ""):
        return True
    if section and text.startswith(section):
        body = text[len(section):].strip()
        if len(body) < body_min:
            return True
    # Single-line heading-sized fragment with no section metadata.
    if section is None and "\n" not in text and len(text) < body_min:
        return True
    return False


def _section_chunks(
    document: ParsedDocument, blocks: list[TextBlock], section: str | None,
    min_chars: int, max_chars: int, overlap: int, offset: int,
) -> list[Chunk]:
    text = ""
    spans: list[tuple[int, int, int]] = []
    for block in blocks:
        if text:
            text += "\n\n"
        start = len(text)
        text += block.text.strip()
        spans.append((start, len(text), block.page))
    paragraphs = [match.start() for match in re.finditer(r"\n\s*\n", text)]
    sentences = [match.end() for match in re.finditer(r"[。！？；]|[.!?;](?=\s|$)", text)]
    chunks: list[Chunk] = []
    start = 0
    target = (min_chars + max_chars) // 2
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            for boundaries in (paragraphs, sentences):
                candidates = boundaries[
                    bisect_left(boundaries, start + min_chars):bisect_right(boundaries, end)
                ]
                if candidates:
                    end = min(candidates, key=lambda point: abs(point - start - target))
                    break
        raw = text[start:end]
        content = raw.strip()
        if content:
            content_start = start + len(raw) - len(raw.lstrip())
            content_end = end - (len(raw) - len(raw.rstrip()))
            pages = [page for left, right, page in spans if left < content_end and right > content_start]
            identity = f"{document.doc_id}:{offset + len(chunks)}:{content_start}:{content_end}:{content}"
            chunks.append(Chunk(
                chunk_id=sha256(identity.encode("utf-8")).hexdigest(),
                doc_id=document.doc_id, file=document.file, text=content,
                page=pages[0], page_end=pages[-1], section=section,
            ))
        if end == len(text):
            break
        # Expand overlap at the end to avoid a tiny trailing chunk. Short
        # sections remain short rather than mixing unrelated headings.
        start = min(end - overlap, max(start + 1, len(text) - min_chars))
    return chunks


def merge_short_chunks(chunks: list[Chunk], *, min_chars: int) -> list[Chunk]:
    """Merge title-only / too-short chunks into the following body; also merge adjacent shorts."""
    if not chunks:
        return []
    threshold = max(1, min_chars // 2)

    def _combine(a: Chunk, b: Chunk) -> Chunk:
        combined = f"{a.text}\n\n{b.text}".strip()
        identity = f"{a.doc_id}:merged:{a.chunk_id}:{b.chunk_id}:{combined}"
        return Chunk(
            chunk_id=sha256(identity.encode("utf-8")).hexdigest(),
            doc_id=a.doc_id,
            file=a.file,
            text=combined,
            page=a.page,
            page_end=b.page_end or b.page,
            section=b.section or a.section,
        )

    # Pass 1: forward-merge title-only / short into the next chunk (same doc).
    forward: list[Chunk] = []
    i = 0
    while i < len(chunks):
        cur = chunks[i]
        if i + 1 < len(chunks) and _is_title_only(cur):
            nxt = chunks[i + 1]
            if cur.doc_id == nxt.doc_id:
                forward.append(_combine(cur, nxt))
                i += 2
                continue
        forward.append(cur)
        i += 1

    # Pass 2: adjacent same-section shorts (previous behaviour).
    merged: list[Chunk] = []
    for chunk in forward:
        if not merged:
            merged.append(chunk)
            continue
        prev = merged[-1]
        same_section = prev.section == chunk.section and prev.doc_id == chunk.doc_id
        if same_section and (len(prev.text) < threshold or len(chunk.text) < threshold):
            merged[-1] = _combine(prev, chunk)
        else:
            merged.append(chunk)
    return merged


def chunk_document(
    document: ParsedDocument, *, min_chars: int = 500, max_chars: int = 800, overlap: int = 100,
) -> list[Chunk]:
    """Split within headings, keeping physical page spans and stable identities.

    Lengths count Python characters (including internal whitespace). Sections
    shorter than min_chars are kept intact. Overlap may grow for the last chunk.
    Directory/TOC pages are dropped before chunking.
    """
    if not 0 <= overlap < min_chars <= max_chars:
        raise ValueError("Require 0 <= overlap < min_chars <= max_chars")
    document = remove_repeated_margins(document)
    document = drop_toc_pages(document)
    chunks: list[Chunk] = []
    group: list[TextBlock] = []
    section: str | None = None
    for page in document.pages:
        for block in page.blocks:
            if not block.text.strip():
                continue
            if block.is_heading:
                if group:
                    chunks.extend(_section_chunks(
                        document, group, section, min_chars, max_chars, overlap, len(chunks),
                    ))
                group = []
                section = block.text.strip()
            group.append(block)
    if group:
        chunks.extend(_section_chunks(
            document, group, section, min_chars, max_chars, overlap, len(chunks),
        ))
    return merge_short_chunks(chunks, min_chars=min_chars)
