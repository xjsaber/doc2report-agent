"""In-memory registry of parsed documents for table/chunk lookup tools."""

from __future__ import annotations

from threading import RLock

from core.parse.models import ParsedDocument

_lock = RLock()
_DOCUMENTS: dict[str, ParsedDocument] = {}


def put_document(document: ParsedDocument) -> None:
    with _lock:
        _DOCUMENTS[document.doc_id] = document


def get_document(doc_id: str) -> ParsedDocument | None:
    with _lock:
        return _DOCUMENTS.get(doc_id)


def clear_documents() -> None:
    with _lock:
        _DOCUMENTS.clear()


def list_document_ids() -> list[str]:
    with _lock:
        return list(_DOCUMENTS.keys())
