"""Citation and numeric claim verification helpers."""

from core.qa.answer import Citation, validate_answer_citations
from core.tools.verify_claim import VerifyClaimInput, verify_claim


def test_citation_verification():
    allowed = [
        Citation(
            file="synthetic.pdf",
            page=2,
            chunk_id="c1",
            text="营业收入 120.5 亿元。",
            score=1.0,
            doc_id="a",
        )
    ]
    ok, err = validate_answer_citations("营收为 120.5 亿元。[synthetic.pdf p2]", allowed)
    assert ok is True and err is None

    bad_page, err = validate_answer_citations("营收上升。[synthetic.pdf p99]", allowed)
    assert bad_page is False
    assert err and "不在本次检索" in err

    missing, err = validate_answer_citations("营收上升但没有引用。", allowed)
    assert missing is False
    assert err and "引用" in err

    supported = verify_claim(
        VerifyClaimInput(claim="营业收入为 120.5 亿元。[synthetic.pdf p2]", source_chunk_ids=["c1"]),
        chunk_lookup={"c1": allowed[0].text},
    )
    assert supported.ok and supported.data.status == "supported"

    mismatch = verify_claim(
        VerifyClaimInput(claim="营业收入为 999 亿元。[synthetic.pdf p2]", source_chunk_ids=["c1"]),
        chunk_lookup={"c1": allowed[0].text},
    )
    assert mismatch.ok and mismatch.data.status == "mismatch"
