"""docs/ Markdown must not contain control characters (e.g. PowerShell backtick escapes)."""

from pathlib import Path
import re

DOCS = Path(__file__).resolve().parents[1] / "docs"
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def test_docs_markdown_has_no_control_characters():
    offenders = []
    for path in sorted(DOCS.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in _CONTROL_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(DOCS)}:{line}:{match.group()!r}")
    assert not offenders, "control characters in docs: " + ", ".join(offenders)


def test_docs_have_no_unfilled_placeholders():
    for path in sorted(DOCS.rglob("*.md")):
        assert "写入本段下方「实跑补充」" not in path.read_text(encoding="utf-8"), path.name
