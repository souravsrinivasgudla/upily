"""
Quality gate: the offline evaluation (no LLM, no network) must not regress.
Floors sit a little under the current scores; see evals/README.md for the numbers.
"""
from evals import run_eval


def test_retrieval_and_grouping_quality_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(run_eval, "RESULTS", tmp_path)   # don't overwrite the committed report
    result = run_eval.main(show_misses=False)

    retrieval = result["retrieval"]
    assert retrieval["easy"]["hit@3"] >= 0.95
    assert retrieval["hard"]["hit@3"] >= 0.50       # vocabulary mismatch is the known weak spot
    assert retrieval["negative"]["reject"] >= 0.60

    grouping = result["grouping"]
    assert grouping["precision"] >= 0.95            # a wrong "3 outlets" badge is worse than a missed one
    assert grouping["recall"] >= 0.80
