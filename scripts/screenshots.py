"""Capture real Streamlit UI screenshots with Playwright (no staged demos).

Usage (from repo root, venv active, model already cached):

    python scripts/screenshots.py --pdf data/samples/public-annual-report-2024.pdf

Requires: pip install -e ".[qa,embedding]" && pip install playwright
Prefers system Chrome/Edge (channel=chrome|msedge) so Playwright browser
download is optional.

Screenshots land in docs/images/. Does not commit PDFs, .env, or output/.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMAGES = REPO / "docs" / "images"


def _start_streamlit(script: Path, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("EMBEDDING_BACKEND", "local")
    env.pop("EMBEDDING_ALLOW_DOWNLOAD", None)
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(script),
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(REPO),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _wait_http(url: str, timeout: float = 120.0) -> None:
    import urllib.request

    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.0)
    raise RuntimeError(f"Streamlit not ready at {url}: {last_err}")


def _launch_browser(playwright):
    """Prefer system Chrome/Edge to avoid downloading Playwright browsers."""
    last_err: Exception | None = None
    for channel in ("chrome", "msedge", None):
        try:
            if channel:
                return playwright.chromium.launch(headless=True, channel=channel)
            return playwright.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    raise RuntimeError(f"Unable to launch Chromium/Chrome/Edge: {last_err}")


def _sidebar_upload(page, pdf: Path) -> None:
    locator = page.locator('input[type="file"]')
    # Streamlit may hide the input; force attach + set files.
    locator.wait_for(state="attached", timeout=60_000)
    locator.set_input_files(str(pdf))
    # Uploader chip shows a truncated name + size.
    page.get_by_text("MB", exact=False).first.wait_for(timeout=60_000)
    page.wait_for_timeout(1000)


def _wait_ingest_documents(page, timeout: float = 600.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = page.inner_text("body")
        after = body.split("已入库文档", 1)[-1] if "已入库文档" in body else ""
        if "暂无文档" not in after[:200] and ("页" in after[:200] and "块" in after[:200]):
            return
        time.sleep(3.0)
    raise RuntimeError("Ingest did not populate sidebar documents in time")


def capture_qa(pdf: Path, port: int = 8501) -> None:
    from playwright.sync_api import sync_playwright

    proc = _start_streamlit(REPO / "app" / "rag.py", port)
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_http(url)
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(2000)

            _sidebar_upload(page, pdf)
            page.get_by_role("button", name="解析并入库").click()
            _wait_ingest_documents(page, timeout=600.0)

            page.get_by_label("提问").fill("公司的主营业务是什么？")
            page.get_by_role("button", name="检索并回答").click()
            page.get_by_text("命中原文", exact=True).wait_for(timeout=300_000)
            if page.get_by_text("检索未找到相关依据", exact=False).count():
                page.screenshot(path=str(IMAGES / "qa-cited.png"), full_page=True)
                raise RuntimeError("Cited capture got a refuse message")
            page.wait_for_timeout(1500)
            page.screenshot(path=str(IMAGES / "qa-cited.png"), full_page=True)

            page.get_by_label("提问").fill("如何移民火星并在那里开设咖啡馆？")
            page.get_by_role("button", name="检索并回答").click()
            page.get_by_text("检索未找到相关依据", exact=False).wait_for(timeout=300_000)
            page.wait_for_timeout(1000)
            if page.get_by_text("命中原文", exact=True).count():
                page.screenshot(path=str(IMAGES / "qa-refuse.png"), full_page=True)
                raise RuntimeError("Refuse UI still shows「命中原文」; aborting")
            page.screenshot(path=str(IMAGES / "qa-refuse.png"), full_page=True)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def capture_report(pdf: Path, port: int = 8502) -> None:
    from playwright.sync_api import sync_playwright

    proc = _start_streamlit(REPO / "app" / "report.py", port)
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_http(url)
        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(2000)

            _sidebar_upload(page, pdf)
            page.get_by_role("button", name="生成报告").click()
            page.wait_for_timeout(8000)
            page.screenshot(path=str(IMAGES / "report-progress.png"), full_page=True)

            page.get_by_text("报告预览", exact=False).wait_for(timeout=900_000)
            page.wait_for_timeout(2000)
            expanders = page.locator("[data-testid='stExpander']")
            if expanders.count() > 0:
                expanders.first.click()
                page.wait_for_timeout(800)
            page.screenshot(path=str(IMAGES / "report-preview.png"), full_page=True)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Real Streamlit screenshots via Playwright.")
    parser.add_argument(
        "--pdf",
        default=str(REPO / "data" / "samples" / "public-annual-report-2024.pdf"),
        help="Public annual-report PDF already on disk (not committed).",
    )
    parser.add_argument("--skip-qa", action="store_true")
    parser.add_argument("--skip-report", action="store_true")
    parser.add_argument("--qa-port", type=int, default=8501)
    parser.add_argument("--report-port", type=int, default=8502)
    args = parser.parse_args(argv)

    pdf = Path(args.pdf).expanduser().resolve()
    if not pdf.is_file():
        print(f"PDF not found: {pdf}", file=sys.stderr)
        return 2
    IMAGES.mkdir(parents=True, exist_ok=True)

    to_capture: list[str] = []
    if not args.skip_qa:
        to_capture.extend(["qa-cited.png", "qa-refuse.png"])
    if not args.skip_report:
        to_capture.extend(["report-progress.png", "report-preview.png"])
    for name in to_capture:
        target = IMAGES / name
        if target.exists():
            target.unlink()

    if not args.skip_qa:
        print("Capturing QA screenshots…")
        capture_qa(pdf, port=args.qa_port)
        print("Wrote qa-cited.png / qa-refuse.png")
    if not args.skip_report:
        print("Capturing report screenshots (long-running)…")
        capture_report(pdf, port=args.report_port)
        print("Wrote report-progress.png / report-preview.png")
    print("Done. Review docs/images/ before committing (no username/path/Key).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
