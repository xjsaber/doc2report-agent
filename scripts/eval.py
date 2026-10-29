"""Minimal retrieval hit-rate eval on a public annual-report PDF (v1).

Annotate a handful of questions with expected page numbers, run hybrid search,
and print hit rate. Results are machine-local observations — never invent numbers.

Example:

    python scripts/eval.py --pdf data/samples/public-annual-report-2024.pdf
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.index import get_retriever
from core.qa import load_dotenv_config
from core.tools.parse_document import ParseDocumentInput, parse_document


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_pages: tuple[int, ...]
    note: str = ""


# Hand-labeled against the public 2024 sample used in r8/r9 (page numbers from PDF).
DEFAULT_CASES: tuple[EvalCase, ...] = (
    EvalCase("公司股票简称、注册地址与法定代表人是什么？", (6,), "公司信息页"),
    EvalCase("公司战略定位与 RFID 主营业务概述", (10,), "战略/业务"),
    EvalCase("报告期营业总收入与归属于母公司所有者的净利润及同比", (13,), "主要财务指标文字"),
    EvalCase("分行业分产品营业收入构成", (18,), "收入与成本表"),
    EvalCase("公司披露的主要风险因素有哪些？", (30,), "可能面对的风险"),
    EvalCase("内部控制体系建设与审计监督", (45,), "内控"),
    EvalCase("合并利润表营业收入本年与上年金额", (71,), "利润表"),
    EvalCase("持续经营能力评估结论", (90,), "持续经营"),
)


def page_hit(hit_pages: list[int], expected: tuple[int, ...]) -> bool:
    """True when any expected page appears in the retrieved page list."""
    wanted = set(expected)
    return any(p in wanted for p in hit_pages)


def evaluate_cases(
    *,
    cases: tuple[EvalCase, ...] | list[EvalCase],
    retriever,
    doc_ids: list[str] | None,
    top_k: int,
) -> dict:
    rows = []
    hits = 0
    for case in cases:
        results = retriever.search(case.question, doc_ids=doc_ids, top_k=top_k, mode="hybrid")
        pages = [int(h.page) for h in results]
        ok = page_hit(pages, case.expected_pages)
        hits += int(ok)
        rows.append(
            {
                "question": case.question,
                "expected_pages": list(case.expected_pages),
                "hit_pages": pages,
                "hit": ok,
                "note": case.note,
            }
        )
    total = len(cases)
    return {
        "total": total,
        "hits": hits,
        "hit_rate": (hits / total) if total else 0.0,
        "top_k": top_k,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal retrieval page hit-rate eval.")
    parser.add_argument("--pdf", required=True, help="Public annual-report PDF (not committed).")
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--out", default="", help="Optional JSON path under output/ (gitignored).")
    parser.add_argument(
        "--download-model",
        action="store_true",
        help="Allow downloading the local embedding model if missing.",
    )
    args = parser.parse_args(argv)

    load_dotenv_config()
    if args.download_model:
        import os

        os.environ["EMBEDDING_ALLOW_DOWNLOAD"] = "1"

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    started = perf_counter()
    parsed = parse_document(ParseDocumentInput(file_path=str(pdf_path)))
    if not parsed.ok or parsed.data is None:
        print(f"parse failed: {parsed.error}", file=sys.stderr)
        return 3

    retriever = get_retriever("memory")
    retriever.index_chunks(parsed.data.chunks)
    report = evaluate_cases(
        cases=DEFAULT_CASES,
        retriever=retriever,
        doc_ids=[parsed.data.doc_id],
        top_k=args.top_k,
    )
    elapsed = perf_counter() - started
    env = {
        "system": platform.system(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "retriever": "memory",
        "pdf": pdf_path.name,
        "chunks": len(parsed.data.chunks),
        "elapsed_seconds": round(elapsed, 1),
    }
    payload = {"env": env, "eval": report}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(
        f"hit_rate={report['hit_rate']:.3f} ({report['hits']}/{report['total']}) "
        f"top_k={args.top_k} elapsed={elapsed:.1f}s "
        f"env={env['system']}/Python {env['python']}/retriever=memory"
    )
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
