"""Unit tests for scripts/eval.py scoring (no PDF, no network)."""

from scripts.eval import EvalCase, evaluate_cases, page_hit


class _Hit:
    def __init__(self, page: int):
        self.page = page


class _FakeRetriever:
    def __init__(self, mapping: dict[str, list[int]]):
        self.mapping = mapping

    def search(self, query, doc_ids=None, top_k=8, mode="hybrid"):
        pages = self.mapping.get(query, [])[:top_k]
        return [_Hit(p) for p in pages]


def test_page_hit():
    assert page_hit([1, 6, 9], (6,))
    assert not page_hit([1, 2], (6, 88))


def test_evaluate_cases_hit_rate():
    cases = [
        EvalCase("q1", (6,)),
        EvalCase("q2", (13, 71)),
        EvalCase("q3", (30,)),
    ]
    retriever = _FakeRetriever({"q1": [6, 1], "q2": [8, 9], "q3": [30]})
    report = evaluate_cases(cases=cases, retriever=retriever, doc_ids=["d"], top_k=2)
    assert report["hits"] == 2
    assert report["total"] == 3
    assert abs(report["hit_rate"] - 2 / 3) < 1e-9
    assert report["rows"][1]["hit"] is False
