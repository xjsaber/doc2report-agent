"""Heading-aware character chunks with paragraph boundaries and overlap."""

from bisect import bisect_left, bisect_right
from hashlib import sha256
import re

from core.models import Chunk
from core.parse.models import ParsedDocument, TextBlock
from core.parse.denoise import remove_repeated_margins


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
    """Merge adjacent same-section chunks when either side is shorter than min_chars/2."""
    if not chunks:
        return []
    threshold = max(1, min_chars // 2)
    merged: list[Chunk] = []
    for chunk in chunks:
        if not merged:
            merged.append(chunk)
            continue
        prev = merged[-1]
        same_section = prev.section == chunk.section and prev.doc_id == chunk.doc_id
        if same_section and (len(prev.text) < threshold or len(chunk.text) < threshold):
            combined = f"{prev.text}\n\n{chunk.text}".strip()
            identity = f"{prev.doc_id}:merged:{prev.chunk_id}:{chunk.chunk_id}:{combined}"
            merged[-1] = Chunk(
                chunk_id=sha256(identity.encode("utf-8")).hexdigest(),
                doc_id=prev.doc_id,
                file=prev.file,
                text=combined,
                page=prev.page,
                page_end=chunk.page_end or chunk.page,
                section=prev.section,
            )
        else:
            merged.append(chunk)
    return merged


def chunk_document(
    document: ParsedDocument, *, min_chars: int = 500, max_chars: int = 800, overlap: int = 100,
) -> list[Chunk]:
    """Split within headings, keeping physical page spans and stable identities.

    Lengths count Python characters (including internal whitespace). Sections
    shorter than min_chars are kept intact. Overlap may grow for the last chunk.
    """
    if not 0 <= overlap < min_chars <= max_chars:
        raise ValueError("Require 0 <= overlap < min_chars <= max_chars")
    document = remove_repeated_margins(document)
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
