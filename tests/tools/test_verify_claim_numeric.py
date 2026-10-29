"""Numeric matching, noise stripping, and calculated-claim recalculation for verify_claim."""

from decimal import Decimal

from core.tools.verify_claim import (
    _extract_claimed_ratio,
    ParsedNumber,
    VerifyClaimInput,
    extract_numbers,
    extract_parsed_numbers,
    is_calculated_claim,
    numbers_equivalent,
    strip_claim_noise,
    verify_calculated_sentence,
    verify_claim,
)


def test_strip_citation_and_markdown_noise():
    raw = "## 3. 营业收入\n1. 营收上升。[public-annual-report-2024.pdf p88]"
    cleaned = strip_claim_noise(raw)
    assert "2024" not in cleaned
    assert "p88" not in cleaned
    assert "88" not in cleaned
    assert not cleaned.strip().startswith("1.")
    assert "##" not in cleaned


def test_citation_year_and_page_not_claim_numbers():
    claim = "内部控制体系已建立。[public-annual-report-2024.pdf p45]"
    assert extract_parsed_numbers(claim) == []
    result = verify_claim(
        VerifyClaimInput(claim=claim, source_chunk_ids=["c1"]),
        chunk_lookup={"c1": "公司建立并健全内部控制体系。"},
    )
    assert result.ok and result.data.status == "supported"


def test_no_digit_sentence_passes_with_valid_citation():
    claim = "公司评估持续经营能力良好。[public-annual-report-2024.pdf p90]"
    result = verify_claim(
        VerifyClaimInput(claim=claim, source_chunk_ids=["c1"]),
        chunk_lookup={"c1": "持续经营能力良好，不存在重大怀疑因素。"},
    )
    assert result.ok and result.data.status == "supported"


def test_wan_yuan_unit_conversion():
    lookup = {"c1": "营业收入 120500000 元。"}
    ok = verify_claim(
        VerifyClaimInput(claim="营业收入为 12050 万元。[a.pdf p1]", source_chunk_ids=["c1"]),
        chunk_lookup=lookup,
    )
    assert ok.ok and ok.data.status == "supported"


def test_yi_yuan_unit_conversion():
    lookup = {"c1": "营业收入 12.05 亿元。"}
    ok = verify_claim(
        VerifyClaimInput(claim="营业收入为 120500 万元。[a.pdf p1]", source_chunk_ids=["c1"]),
        chunk_lookup=lookup,
    )
    assert ok.ok and ok.data.status == "supported"


def test_percent_precision_rounding():
    assert numbers_equivalent(
        ParsedNumber(value=Decimal("12.3"), is_percent=True, raw="12.3%", precision=1, unit=None),
        ParsedNumber(value=Decimal("12.30"), is_percent=True, raw="12.30%", precision=2, unit=None),
    )
    lookup = {"c1": "营业收入同比 -9.248%"}
    ok = verify_claim(
        VerifyClaimInput(claim="营业收入同比为 -9.25%。[a.pdf p18]", source_chunk_ids=["c1"]),
        chunk_lookup=lookup,
    )
    # -9.25 vs -9.248 rounded to 2 decimals
    assert ok.ok and ok.data.status == "supported"


def test_thousand_separator_match():
    lookup = {"c1": "营业收入 572581433.98 元"}
    ok = verify_claim(
        VerifyClaimInput(
            claim="主营业务收入为 572,581,433.98 元。[a.pdf p154]",
            source_chunk_ids=["c1"],
        ),
        chunk_lookup=lookup,
    )
    assert ok.ok and ok.data.status == "supported"


def test_bare_substring_fallback_removed():
    """Digit '8' appearing inside unrelated text must not count as support."""
    lookup = {"c1": "章节编号见附录表A8说明，无营收数字。"}
    bad = verify_claim(
        VerifyClaimInput(claim="营业收入为 8 亿元。[a.pdf p1]", source_chunk_ids=["c1"]),
        chunk_lookup=lookup,
    )
    assert bad.ok and bad.data.status == "mismatch"


def test_true_wrong_number_still_mismatch():
    lookup = {"c1": "营业收入 120.5 亿元，净利润 30 亿元。"}
    bad = verify_claim(
        VerifyClaimInput(claim="营业收入为 999 亿元。[a.pdf p1]", source_chunk_ids=["c1"]),
        chunk_lookup=lookup,
    )
    assert bad.ok and bad.data.status == "mismatch"


def test_calculated_claim_recompute_gross_margin():
    claim = "毛利率为 41.51%。（据第 18 页数据计算）[a.pdf p18]"
    assert is_calculated_claim(claim)
    evidence = ["营业收入 521803949.48 元，营业成本 305205137.94 元"]
    status, diff = verify_calculated_sentence(claim, evidence)
    assert status == "supported", diff


def test_calculated_claim_mismatch_when_wrong():
    claim = "毛利率为 99.00%。（据第 18 页数据计算）"
    evidence = ["营业收入 100 元，营业成本 50 元"]
    status, diff = verify_calculated_sentence(claim, evidence)
    assert status == "mismatch"
    assert diff and "毛利率" in diff


def test_calculated_claim_via_verify_claim():
    lookup = {"c1": "营业收入 100 万元，营业成本 60 万元"}
    ok = verify_claim(
        VerifyClaimInput(
            claim="毛利率为 40.00%。（据第 3 页数据计算）[a.pdf p3]",
            source_chunk_ids=["c1"],
        ),
        chunk_lookup=lookup,
    )
    assert ok.ok and ok.data.status == "supported"


def test_extract_numbers_ignores_list_index():
    text = "1. 实物销售收入是否大于劳务收入的选择为「是」"
    # After stripping list marker, remaining text has no digits.
    assert extract_numbers(text) == []


def test_net_margin_ignores_prior_yoy_decline_percent():
    """r10: 「下降 0.95%」 must not be bound as the 净利率 claim when 5.10% follows."""
    claim = (
        "归属于母公司所有者的净利润为 2,784.78 万元，较上年同期下降 0.95% [a.pdf p13]；"
        "按归母净利润口径计算的净利率为 5.10%（据第 13、71 页数据计算）[a.pdf p13][a.pdf p71]。"
    )
    kind, claimed = _extract_claimed_ratio(claim)
    assert kind == "净利率"
    assert claimed is not None and claimed.raw == "5.10%"
    evidence = [
        "营业总收入（元）\n545,680,493.10\n601,286,596.33\n"
        "归属于母公司所有者的净利润（元）\n27,847,800.00\n28,114,000.00"
    ]
    # Pre-fix behaviour was mismatch (0.95 vs 5.10); post-fix must be supported.
    status, diff = verify_calculated_sentence(claim, evidence)
    assert status == "supported", diff
    lookup = {"c1": evidence[0], "c2": evidence[0]}
    out = verify_claim(
        VerifyClaimInput(claim=claim, source_chunk_ids=["c1", "c2"]),
        chunk_lookup=lookup,
    )
    assert out.ok and out.data.status == "supported", out.data.difference if out.data else out.error


def test_yoy_percent_still_binds_when_no_net_margin_keyword():
    kind, claimed = _extract_claimed_ratio(
        "营业收入同比增速为 -9.25%（据第 71 页数据计算）[a.pdf p71]"
    )
    assert kind == "同比"
    assert claimed is not None and "-9.25%" in claimed.raw

