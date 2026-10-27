"""Original synthetic PDFs, created only inside pytest's temporary directory."""

import pymupdf
import pytest


@pytest.fixture(autouse=True)
def memory_default(monkeypatch):
    monkeypatch.setenv("RETRIEVER", "memory")
    monkeypatch.setenv("EMBEDDING_BACKEND", "fake")


@pytest.fixture
def sample_pdf(tmp_path):
    path = tmp_path / "synthetic.pdf"
    with pymupdf.open() as pdf:
        for number in range(2):
            page = pdf.new_page()
            if number == 0:
                page.insert_text((50, 60), "第一节 公司概况", fontname="china-s", fontsize=18)
            for paragraph in range(2):
                text = f"公司业务段落{number * 2 + paragraph}：" + "公司坚持自主研发并服务客户，主营业务保持稳定发展。" * 13
                remaining = page.insert_textbox(
                    (50, 100 + paragraph * 230, 540, 310 + paragraph * 230),
                    text, fontname="china-s", fontsize=10,
                )
                assert remaining >= 0, "Synthetic paragraph must fit on the page"
        page = pdf.new_page()
        page.insert_text((50, 60), "第二节 财务表现", fontname="china-s", fontsize=18)
        page.insert_text((50, 120), "Financial summary", fontsize=10)
        for x in (50, 250, 400):
            page.draw_line((x, 150), (x, 240))
        for y in (150, 180, 210, 240):
            page.draw_line((50, y), (400, y))
        for row, cells in enumerate((("Metric", "Value"), ("Revenue", "120"), ("Profit", "30"))):
            for column, text in enumerate(cells):
                page.insert_text((60 + column * 200, 170 + row * 30), text, fontsize=10)
        pdf.save(path)
    return path
