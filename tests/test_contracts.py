"""Only validate schema wiring; business behavior remains unimplemented."""

from importlib import import_module
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from core.models import Chunk, SearchHit, ToolResult
from core.graph.state import ReportState, SectionState
from core.index.retriever import Retriever
from core.tools.search_chunks import SearchChunksInput, search_chunks

MODULES = ["parse_document", "search_chunks", "get_table", "calc_financials",
           "verify_claim", "render_section", "export_report", "templates"]


@pytest.mark.parametrize("module", MODULES)
def test_tool_schema_can_be_exported(module):
    namespace = vars(import_module(f"core.tools.{module}"))
    for name, model in namespace.items():
        if name.endswith(("Input", "Output")):
            assert model.model_json_schema()["type"] == "object"


def test_shared_envelope_serialization():
    result = ToolResult[dict](ok=False, error="not implemented")
    assert result.model_dump() == {
        "ok": False, "data": None, "error": "not implemented", "sources": []
    }


def test_success_result_rejects_error():
    assert ToolResult[dict](ok=True, data={"pages": 1}).error is None
    for error in ("failed", ""):
        with pytest.raises(ValidationError, match="must not contain an error"):
            ToolResult[dict](ok=True, data={}, error=error)


@pytest.mark.parametrize("error,data", [(None, None), ("", None), ("  ", None), ("failed", {})])
def test_failure_result_requires_error_and_empty_data(error, data):
    with pytest.raises(ValidationError):
        ToolResult[dict](ok=False, error=error, data=data)


def test_chunk_and_search_hit_keep_document_and_page_range():
    chunk = Chunk(doc_id="doc", chunk_id="chunk", file="sample.pdf", page=2, text="text")
    assert chunk.page_end == 2
    assert chunk.section is None
    assert Chunk(**{**chunk.model_dump(), "page_end": None}).page_end == 2
    hit = SearchHit(**chunk.model_dump(), score=0.9)
    assert hit.doc_id == "doc"
    with pytest.raises(ValidationError, match="page_end"):
        Chunk(**{**chunk.model_dump(), "page_end": 1})


def test_retrieval_boundary_and_defaults():
    assert get_type_hints(search_chunks)["retriever"] is Retriever
    assert SearchChunksInput(query="revenue").model_dump() == {
        "query": "revenue", "doc_ids": None, "top_k": 8, "mode": "hybrid"
    }


def test_graph_state_annotations_resolve():
    assert "sections" in get_type_hints(ReportState)
    assert "rewrite_count" in get_type_hints(SectionState)
