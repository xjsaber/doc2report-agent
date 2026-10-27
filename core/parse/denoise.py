"""Conservative cross-page margin filtering before chunking; originals stay intact."""

from collections import Counter
from math import ceil
import re

from core.parse.models import ParsedDocument, TextBlock, collect_sections


def _key(text: str) -> str:
    text = " ".join(text.split())
    # Normalize only standalone page labels, never numbers within body sentences.
    if re.fullmatch(r"(?:第\s*)?\d+\s*(?:页)?|[-—]\s*\d+\s*[-—]", text):
        return "<page-number>"
    return text


def remove_repeated_margins(document: ParsedDocument) -> ParsedDocument:
    """Remove edge occurrences on >=30% of all pages, requiring two distinct pages.

    PDF candidates come from the top/bottom 10% of page height. Without layout,
    use the first/last nonblank lines only when at least three lines exist.
    """
    candidates: list[set[str]] = []
    for page in document.pages:
        lines = [line.strip() for block in page.blocks for line in block.text.splitlines() if line.strip()]
        edges = page.margin_lines
        if edges is None:
            edges = [lines[0], lines[-1]] if len(lines) >= 3 else []
        candidates.append({_key(line) for line in edges if line.strip()})
    counts = Counter(key for keys in candidates for key in keys)
    threshold = max(2, ceil(len(document.pages) * 0.30))
    repeated = {key for key, count in counts.items() if count >= threshold}
    cleaned = document.model_copy(deep=True)
    for page, keys in zip(cleaned.pages, candidates):
        flattened = [(i, line) for i, block in enumerate(page.blocks)
                     for line in block.text.splitlines() if line.strip()]
        # Only strip contiguous edge lines; identical text inside the body survives.
        remove: set[int] = set()
        for indices in (range(len(flattened)), range(len(flattened) - 1, -1, -1)):
            for index in indices:
                if _key(flattened[index][1]) not in repeated & keys:
                    break
                remove.add(index)
        kept: dict[int, list[str]] = {}
        for index, (block_index, line) in enumerate(flattened):
            if index not in remove:
                kept.setdefault(block_index, []).append(line)
        page.blocks = [TextBlock(text="\n".join(lines), page=page.page,
                                 is_heading=page.blocks[i].is_heading) for i, lines in kept.items()]
        page.text = "\n\n".join(block.text for block in page.blocks)
    cleaned.sections = collect_sections(cleaned.pages)
    return cleaned
