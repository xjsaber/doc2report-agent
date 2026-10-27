"""In-memory PDF content, with one-based physical page numbers."""

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    text: str
    page: int = Field(ge=1)
    is_heading: bool = False


class ParsedPage(BaseModel):
    page: int = Field(ge=1)
    text: str
    blocks: list[TextBlock] = Field(default_factory=list)
    margin_lines: list[str] | None = None


class Section(BaseModel):
    title: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)


class ParsedTable(BaseModel):
    table_id: str
    page: int = Field(ge=1)
    caption: str | None = None
    headers: list[str]
    rows: list[list[str]]
    raw_text: str


class ParsedDocument(BaseModel):
    doc_id: str
    file: str
    engine: str
    pages: list[ParsedPage]
    sections: list[Section]
    tables: list[ParsedTable]


def collect_sections(pages: list[ParsedPage]) -> list[Section]:
    """A section ends at its last content page, before the next heading."""
    sections: list[Section] = []
    for page in pages:
        for block in page.blocks:
            if block.is_heading:
                sections.append(Section(title=block.text, page_start=block.page, page_end=block.page))
            elif sections:
                sections[-1].page_end = block.page
    return sections
