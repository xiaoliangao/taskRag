from __future__ import annotations

from app.eval.run_eval import summarize_faithfulness


def test_summary_counts_unfaithful_and_failures_separately():
    results = [
        {"score": 1.0},
        {"score": 0.8},
        {"score": 0.3},          # unfaithful (< 0.5)
        {"score": None, "error": "gen_failed"},  # failure, not a 0
    ]
    s = summarize_faithfulness(results, gen_top_n=5)
    assert s["n_judged"] == 4
    assert s["failed"] == 1
    assert s["unfaithful_count"] == 1
    # mean over the 3 real scores, NOT dragged down by the failed one.
    assert abs(s["mean"] - round((1.0 + 0.8 + 0.3) / 3, 3)) < 1e-9
    assert s["gen_top_n"] == 5


def test_summary_all_failed_yields_none_mean():
    results = [{"score": None}, {"score": None}]
    s = summarize_faithfulness(results, gen_top_n=3)
    assert s["mean"] is None
    assert s["failed"] == 2
    assert s["unfaithful_count"] == 0


def test_summary_empty():
    s = summarize_faithfulness([], gen_top_n=5)
    assert s["n_judged"] == 0
    assert s["mean"] is None
