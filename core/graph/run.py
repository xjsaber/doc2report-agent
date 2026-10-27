"""CLI: python -m core.graph.run --pdf <path> [--template company_analysis]."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from core.index import get_retriever
from core.qa import build_chat_model, load_dotenv_config
from core.tools.parse_document import ParseDocumentInput, parse_document
from core.tools.export_report import ExportReportInput, export_report
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
    title = state.get("title") or args.title or "年报分析"
    md_res = export_report(
        ExportReportInput(report_md=report_md, format="md", title=title, output_dir=str(out_dir))
    )
    docx_res = export_report(
        ExportReportInput(report_md=report_md, format="docx", title=title, output_dir=str(out_dir))
    )
    if md_res.ok and md_res.data:
        print(f"Wrote {md_res.data.file_path} ({len(report_md)} chars).")
    else:
        print(f"Markdown export failed: {md_res.error}", file=sys.stderr)
    if docx_res.ok and docx_res.data:
        print(f"Wrote {docx_res.data.file_path}")
    else:
        print(f"Word export failed: {docx_res.error}", file=sys.stderr)
    # Keep export paths on state for callers.
    paths = []
    if md_res.ok and md_res.data:
        paths.append(md_res.data.file_path)
    if docx_res.ok and docx_res.data:
        paths.append(docx_res.data.file_path)
    state["export_paths"] = paths
    errors = state.get("errors") or []
    if errors:
        print("Completed with notes:")
        for err in errors:
            print(f"- {err}")
    return 0 if md_res.ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
