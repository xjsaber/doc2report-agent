"""Export sentence-level verify debug JSON for an existing report.md (not committed)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.qa.answer import parse_citation_markers
from core.tools.parse_document import ParseDocumentInput, parse_document
from core.tools.verify_claim import debug_verify_sentence, split_claim_sentences, strip_claim_noise

_PENDING = "【待核实】"


def has_claim_digits(piece: str) -> bool:
    """Same gate as the graph verify node: only sentences with digits after noise stripping."""
    return bool(re.search(r"\d", strip_claim_noise(piece)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="output/e2e/report.md")
    parser.add_argument("--pdf", default="data/samples/public-annual-report-2024.pdf")
    parser.add_argument("--out", default="output/verify-debug.json")
    args = parser.parse_args()

    report_path = Path(args.report)
    pdf_path = Path(args.pdf)
    if not report_path.is_file():
        print(f"missing report: {report_path}", file=sys.stderr)
        return 2
    if not pdf_path.is_file():
        print(f"missing pdf: {pdf_path}", file=sys.stderr)
        return 3

    report_md = report_path.read_text(encoding="utf-8")
    parsed = parse_document(ParseDocumentInput(file_path=str(pdf_path)))
    if not parsed.ok or parsed.data is None:
        print(parsed.error, file=sys.stderr)
        return 4

    by_page: dict[tuple[str, int], list[str]] = {}
    by_chunk: dict[str, str] = {}
    for chunk in parsed.data.chunks:
        by_page.setdefault((chunk.file, chunk.page), []).append(chunk.text)
        by_chunk[chunk.chunk_id] = chunk.text

    rows = []
    for piece in split_claim_sentences(report_md):
        if not piece or piece.startswith("#"):
            continue
        if not has_claim_digits(piece):
            continue
        markers = parse_citation_markers(piece)
        evidence: list[str] = []
        for file_name, page in markers:
            evidence.extend(by_page.get((file_name, page), []))
        if not evidence and markers:
            # page exists but empty — still record
            pass
        if not markers and not re.search(r"\d", piece):
            continue
        detail = debug_verify_sentence(piece, evidence)
        detail["markers"] = [{"file": f, "page": p} for f, p in markers]
        detail["had_pending_mark"] = _PENDING in piece
        rows.append(detail)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "report": str(report_path),
        "sentences": len(rows),
        "supported": sum(1 for r in rows if r["status"] == "supported"),
        "mismatch": sum(1 for r in rows if r["status"] == "mismatch"),
        "not_found": sum(1 for r in rows if r["status"] == "not_found"),
        "had_pending_mark": sum(1 for r in rows if r["had_pending_mark"]),
        "rows": rows,
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"wrote {out_path} sentences={summary['sentences']} "
        f"supported={summary['supported']} mismatch={summary['mismatch']} "
        f"not_found={summary['not_found']} pending_marks={summary['had_pending_mark']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
