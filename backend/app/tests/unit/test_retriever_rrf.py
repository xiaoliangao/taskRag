"""Unit tests for RRF fusion in retriever (Sprint 6 Hybrid Search)."""
from __future__ import annotations

from app.rag.retriever import _rrf_fuse


def test_rrf_single_ranking_returns_decreasing_scores():
    ranking = [(101, 0.9), (102, 0.5), (103, 0.1)]
    scores = _rrf_fuse([ranking], k=60)
    assert scores[101] > scores[102] > scores[103]


def test_rrf_combines_two_rankings_doc_in_both_wins():
    # Doc 101 appears in both rankings; doc 999 in only one.
    bm25 = [(101, 1.0), (999, 0.5), (103, 0.1)]
    vec = [(101, 0.9), (104, 0.7), (105, 0.4)]
    scores = _rrf_fuse([bm25, vec], k=60)
    # 101 ranks #1 in both -> 2 * 1/(60+1) ≈ 0.0328
    # 999 ranks only #2 in BM25 -> 1/(60+2) ≈ 0.0161
    assert scores[101] > scores[999]
    # documents present in only one ranking still get scored
    assert 103 in scores and 104 in scores and 105 in scores


def test_rrf_empty_rankings_returns_empty():
    assert _rrf_fuse([], k=60) == {}
    assert _rrf_fuse([[], []], k=60) == {}


def test_rrf_k_dampens_higher_ranks():
    ranking = [(1, 0.99), (2, 0.5)]
    sk_small = _rrf_fuse([ranking], k=1)
    sk_large = _rrf_fuse([ranking], k=100)
    # With k=1, the gap between rank 1 and rank 2 is huge (1/2 vs 1/3).
    # With k=100, the gap shrinks (1/101 vs 1/102).
    assert (sk_small[1] - sk_small[2]) > (sk_large[1] - sk_large[2])
