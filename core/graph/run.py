"""CLI: python -m core.graph.run --pdf <path> [--template company_analysis]."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

from core.index import get_retriever
from core.qa import build_chat_model, load_dotenv_config
from core.tools.parse_document import ParseDocumentInput, parse_document
from core.graph.workflow import run_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a source-backed annual-report analysis draft.")
    parser.add_argument("--pdf", required=True, help="Path to a public annual-report PDF (not committed).")
    parser.add_argument("--template", default="company_analysis", help="Template id under templates/.")
    parser.add_argument("--title", default="", help="Optional report title override.")
    parser.add_argument("--out-dir", default="output", help="Directory for Markdown output (gitignored).")
    parser.add_argument("--top-k", type=int, default=6)
    args = parser.parse_args(argv)

    load_dotenv_config()
    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    print(f"Parsing {pdf_path.name} ...")
    parsed = parse_document(ParseDocumentInput(file_path=str(pdf_path)))
    if not parsed.ok or parsed.data is None:
        print(f"parse failed: {parsed.error}", file=sys.stderr)
        return 3

    retriever = get_retriever("memory")
    retriever.index_chunks(parsed.data.chunks)
    print(f"Indexed {len(parsed.data.chunks)} chunks (doc_id={parsed.data.doc_id[:12]}…).")

    model = build_chat_model()
    if model is None:
        print(
            "API_KEY is not set. Put it in a local .env (never commit). "
            "Aborting model generation; retrieval index was built successfully.",
            file=sys.stderr,
        )
        return 4

    print("Running LangGraph plan→retrieve→write→verify→assemble ...")
    state = run_report(
        retriever=retriever,
        chat_model=model,
        doc_ids=[parsed.data.doc_id],
        template_id=args.template,
        title=args.title or None,
        top_k=args.top_k,
    )
    report_md = state.get("report_md") or ""
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"report-{stamp}.md"
    out_path.write_text(report_md, encoding="utf-8")
    print(f"Wrote {out_path} ({len(report_md)} chars).")
    errors = state.get("errors") or []
    if errors:
        print("Completed with notes:")
        for err in errors:
            print(f"- {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
