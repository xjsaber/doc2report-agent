"""Regression tests: years must never be extracted as revenue / amounts (r7 year-fix)."""

from decimal import Decimal

import pytest

from core.graph.workflow import _try_build_calc_context
from core.tools.financial_extract import extract_financial_rows, extract_row, METRIC_LABELS
from core.tools.verify_claim import (
    VerifyClaimInput,
    extract_parsed_numbers,
    recalculate_ratio,
    verify_calculated_sentence,
    verify_claim,
)

REVENUE = METRIC_LABELS["营业收入"]


def _hit(text: str, page: int = 13, chunk_id: str = "c1", file: str = "public-annual-report-2024.pdf") -> dict:
    return {"text": text, "page": page, "chunk_id": chunk_id, "file": file, "score": 1.0, "doc_id": "d"}


@pytest.mark.parametrize(
    "text",
    [
        "营业收入 2024",
        "营业收入 2023年",
        "营业收入 2024 年度",
        "营业收入（元） 2024 年 2023 年",
        "营业收入\n2024 年\n\n2023 年\n\n同比增减",
    ],
)
def test_year_alone_is_not_revenue(text):
    assert extract_row(text, REVENUE) is None
    assert "营业收入" not in extract_financial_rows([text])


@pytest.mark.parametrize(
    "text",
    [
        "营业收入 2024年度 1,234,567,890.12",
        "2024 年 营业收入 2024 1,234,567,890.12",
        "营业收入 2024 年度 1,234,567,890.12 元",
        "营业收入（元）\n2024年\n1,234,567,890.12",
    ],
)
def test_year_header_skipped_real_amount_kept(text):
    row = extract_financial_rows([text])["营业收入"]
    assert row.current == Decimal("1234567890.12")


def test_review_repro_gross_margin_not_from_year():
    hits = [
        _hit("2024年 营业收入 2024年度 1,234,567,890.12", page=13, chunk_id="a"),
        _hit("营业成本 987,654,321.00", page=13, chunk_id="b"),
    ]
    context = _try_build_calc_context({"chunks": hits})
    assert "毛利率 = 20.00%" in context
    assert "-48797050" not in context
    assert "据第 13 页数据计算" in context

    texts = [h["text"] for h in hits]
    bad = "毛利率为-48797050.25%（据第 13 页数据计算）[public-annual-report-2024.pdf p13]"
    good = "毛利率为20.00%（据第 13 页数据计算）[public-annual-report-2024.pdf p13]"
    assert verify_calculated_sentence(bad, texts)[0] == "mismatch"
    assert verify_calculated_sentence(good, texts)[0] == "supported"


def test_label_at_chunk_end_does_not_take_next_chunk_year():
    # Shape seen in the public sample report: section title + unit header end one chunk,
    # the next chunk starts with the "2024 年 / 2023 年" column headers.
    chunks = [
        "2、收入与成本\n\n（1） 营业收入构成\n\n单位：元",
        "2024 年\n\n2023 年\n\n同比增减\n金额\n占营业收入比重\n金额\n占营业收入比重\n\n"
        "营业收入合计\n545,680,493.10\n100%\n601,286,596.33\n100%\n-9.25%",
    ]
    row = extract_financial_rows(chunks)["营业收入"]
    assert row.current == Decimal("545680493.10")
    assert row.previous == Decimal("601286596.33")
    # Old code read 2024 as revenue and "（1）" as cost -> 99.95% gross margin.
    assert recalculate_ratio("毛利率", "\n".join(chunks)) is None


def test_vertical_table_row_current_previous_and_yoy():
    text = "营业收入（元）\n545,680,493.10\n601,286,596.33\n-9.25%\n480,859,008.51"
    row = extract_financial_rows([_hit(text, page=7)])["营业收入"]
    assert (row.current, row.previous, row.page) == (Decimal("545680493.10"), Decimal("601286596.33"), 7)
    claim = "营业收入同比下降 -9.25%（据第 7 页数据计算）[public-annual-report-2024.pdf p7]"
    assert verify_calculated_sentence(claim, [text])[0] == "supported"


def test_wrapped_label_and_non_recurring_row_rejected():
    text = (
        "归属于上市公司股东的扣除\n非经常性损益的净利润\n（元）\n-135,618,117.77\n\n"
        "归属于上市公司股东的净利\n润（元）\n27,847,758.47\n28,115,967.02\n-0.95%"
    )
    row = extract_financial_rows([text])["净利润"]
    assert row.current == Decimal("27847758.47")


@pytest.mark.parametrize(
    "text",
    [
        "（2） 占公司营业收入或营业利润10%以上的行业",
        "研发投入占营业收入比例 3.37%",
        "营业收入扣除金额（元）\n23,876,543.62",
        "营业收入构成 第 18 页",
    ],
)
def test_non_row_mentions_are_ignored(text):
    assert extract_row(text, REVENUE) is None


def test_units_from_header_label_and_suffix():
    assert extract_financial_rows(["单位：万元\n营业收入 54,568.05"])["营业收入"].current == Decimal("545680500.00")
    assert extract_financial_rows(["营业收入（万元） 54,568.05"])["营业收入"].current == Decimal("545680500.00")
    prose = "报告期内公司实现营业收入54,568.05万元，同比下降9.25%"
    assert extract_financial_rows([prose])["营业收入"].current == Decimal("545680500.00")


def test_amount_with_explicit_unit_still_counts_even_if_year_like():
    assert extract_financial_rows(["营业收入 2024 元"])["营业收入"].current == Decimal("2024")
    assert extract_financial_rows(["营业收入 2,024 万元"])["营业收入"].current == Decimal("20240000")


def test_calc_context_uses_real_sources_and_drops_implausible_ratio():
    good = _try_build_calc_context(
        {"chunks": [_hit("营业收入（元）\n100.00\n80.00", page=7), _hit("营业成本 60.00 元", page=19, chunk_id="c2")]}
    )
    assert "毛利率 = 40.00%" in good
    assert "所用页码：7、19" in good
    assert "据第 1 页" not in good
    bad = _try_build_calc_context({"chunks": [_hit("营业收入 100 元，营业成本 1,000 元")]})
    assert "毛利率" not in bad
    status, _ = verify_calculated_sentence("毛利率为-900.00%（据第 13 页数据计算）", ["营业收入 100 元，营业成本 1,000 元"])
    assert status != "supported"


def test_verify_numbers_ignore_bare_year_and_dates():
    nums = [p.raw for p in extract_parsed_numbers("2024 营业收入 5.46 亿元，截至2024年12月31日")]
    assert nums == ["5.46 亿元"]
    lookup = {"c1": "2024 年度 营业收入 546,000,000 元"}
    out = verify_claim(
        VerifyClaimInput(claim="2024 年度营业收入为 5.46 亿元。[a.pdf p7]", source_chunk_ids=["c1"]),
        chunk_lookup=lookup,
    )
    assert out.ok and out.data.status == "supported"


@pytest.mark.parametrize(
    "text",
    [
        "营业收入 2024年 2023年 本年比上年增减 545,680,493.10 601,286,596.33 -9.25%",
        "营业收入（元） 2024 年 2023 年 本年比上年增减(%) 545,680,493.10 601,286,596.33 -9.25%",
        "营业收入 本期 上年同期 增减变动幅度（%） 545,680,493.10 601,286,596.33 -9.25%",
        "营业收入\n2024年\n2023年\n本年比上年增减\n545,680,493.10\n601,286,596.33\n-9.25%",
    ],
)
def test_horizontal_header_with_change_column(text):
    row = extract_financial_rows([text])["营业收入"]
    assert row.current == Decimal("545680493.10")
    assert row.previous == Decimal("601286596.33")


def test_parenthesized_negative_is_known_limitation():
    """已知局限：括号负数（12,345,678.90）暂不支持，返回空而不是误读成正数。"""
    assert extract_row("净利润（12,345,678.90）", METRIC_LABELS["净利润"]) is None


QUARTERLY_P8 = (
    "八、分季度主要财务指标\n\n单位：元\n\n第一季度\n第二季度\n第三季度\n第四季度\n\n"
    "营业收入\n109,111,915.36\n137,720,578.61\n128,948,286.99\n169,899,712.14\n\n"
    "归属于上市公司股东的净利润\n86,585,831.40\n-42,162,397.68\n18,897,859.99\n-35,473,535.24\n"
)


def test_quarterly_table_is_not_current_vs_previous():
    """r8 E2E: p8 quarterly columns were read as 本期/上期 (营收同比 -20.77%, 净利率 79.36%)."""
    from core.tools.financial_extract import is_quarterly_table
    from core.tools.verify_claim import recalculate_ratio

    assert is_quarterly_table(QUARTERLY_P8)
    assert extract_financial_rows([QUARTERLY_P8], ("营业收入", "净利润")) == {}
    assert recalculate_ratio("同比", [QUARTERLY_P8], claim="营业收入同比") is None
    assert recalculate_ratio("净利率", [QUARTERLY_P8]) is None
    assert not is_quarterly_table("营业收入 2024年 2023年 545,680,493.10 601,286,596.33")
