"""Positive/error case slots; no simulated business success."""
import pytest


@pytest.mark.parametrize("tool", [
    "parse_document", "search_chunks", "get_table", "calc_financials",
    "verify_claim", "render_section", "export_report", "list_templates", "load_template",
])
@pytest.mark.parametrize("case", ["success", "error"])
@pytest.mark.skip(reason="Step 1: business implementation deferred")
def test_tool_behavior(tool, case):
    pass
