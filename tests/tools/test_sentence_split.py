"""r8: citation marks written after the full stop belong to the previous sentence."""

from core.tools.verify_claim import VerifyClaimInput, split_claim_sentences, verify_claim

F = "public-annual-report-2024.pdf"


def test_trailing_marker_after_full_stop_attaches_to_previous_sentence():
    md = (
        f"归属于母公司所有者的净利润为2,784.78万元，较上年同期下降0.95%。[{F} p13] "
        f"经公司评估，自本报告期末起12个月内持续经营能力良好。【待核实】[{F} p90]\n"
    )
    pieces = split_claim_sentences(md)
    assert pieces[0].endswith(f"[{F} p13]")
    assert pieces[1].startswith("经公司评估")
    assert pieces[1].endswith(f"[{F} p90]")
    assert "【待核实】" in pieces[1]
    # Pieces stay contiguous substrings so verify can str.replace them.
    assert all(piece in md for piece in pieces)


def test_marker_before_full_stop_unchanged():
    md = f"营业收入为545,680,493.10元 [{F} p71]。营业利润为20,464,643.71元 [{F} p72]。"
    assert split_claim_sentences(md) == [
        f"营业收入为545,680,493.10元 [{F} p71]。",
        f"营业利润为20,464,643.71元 [{F} p72]。",
    ]


def test_marker_does_not_cross_newline():
    md = f"第一段结束。\n[{F} p3] 第二段。"
    pieces = split_claim_sentences(md)
    assert pieces[0] == "第一段结束。"
    assert pieces[1].startswith(f"[{F} p3]")


def test_r6_company_overview_pattern_now_supported():
    """r6 公司概况 mismatch: '12' was checked against p13 because p13's marker followed the 。."""
    md = (
        f"归属于母公司所有者的净利润为2,784.78万元，较上年同期下降0.95%。[{F} p13] "
        f"经公司评估，自本报告期末起12个月内，公司持续经营能力良好。[{F} p90]"
    )
    lookup = {
        "c13": "归属于母公司所有者的净利润为 2,784.78 万元，较上年同期下降 0.95%。",
        "c90": "公司自本报告期末起 12 个月内持续经营能力良好。",
    }
    pages = {13: "c13", 90: "c90"}
    from core.qa.answer import parse_citation_markers

    for piece in split_claim_sentences(md):
        ids = [pages[p] for _, p in parse_citation_markers(piece)]
        result = verify_claim(VerifyClaimInput(claim=piece, source_chunk_ids=ids), chunk_lookup=lookup)
        assert result.ok and result.data is not None
        assert result.data.status == "supported", (piece, result.data.difference)


def test_multi_page_calc_mark_is_recalculated():
    """r8 E2E 财务表现: '（据第13页、第71页数据计算）' was not seen as a calc mark -> 5.10% mismatch."""
    from core.tools.verify_claim import calc_mark_page, is_calculated_claim, verify_calculated_sentence

    claim = (
        "按归母净利润 2,784.78 万元与营业收入 545,680,493.10 元计算，净利率为 5.10% "
        f"[{F} p13][{F} p71]（据第13页、第71页数据计算）。"
    )
    assert is_calculated_claim(claim)
    assert calc_mark_page(claim) == 13
    assert calc_mark_page("净利率为5.10%（据第13、71页数据计算）。") == 13
    assert calc_mark_page("净利率为5.10%（据第 13 页数据计算）。") == 13
    evidence = [
        "报告期内，公司实现营业总收入54,568.05 万元，较上年同期下降9.25%。"
        "归属于母公司所有者的净利润为\n2,784.78 万元，较上年同期下降0.95%。",
        "一、营业总收入\n\n545,680,493.10\n601,286,596.33",
    ]
    status, diff = verify_calculated_sentence(claim, evidence)
    assert status == "supported", diff
