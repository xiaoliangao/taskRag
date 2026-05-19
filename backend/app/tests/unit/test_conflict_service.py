"""Unit tests for conflict candidate scoring (Sprint 2 Conflict Explorer)."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.conflict_service import _build_candidates, _candidate_score, _normalize


def _claim(**kwargs) -> SimpleNamespace:
    base = dict(
        id=1,
        document_id=10,
        claim_type="result",
        method=None,
        dataset=None,
        metric=None,
        polarity="neutral",
        claim_text="",
        evidence_text=None,
        setting=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_normalize_collapses_whitespace_and_lowercases():
    assert _normalize("  KITTI  2015 ") == "kitti 2015"
    assert _normalize(None) == ""
    assert _normalize("") == ""


def test_same_doc_returns_zero_score():
    a = _claim(id=1, document_id=10, dataset="KITTI", metric="EPE")
    b = _claim(id=2, document_id=10, dataset="KITTI", metric="EPE")
    assert _candidate_score(a, b) == 0.0


def test_same_dataset_and_metric_boost_score():
    a = _claim(id=1, document_id=10, dataset="KITTI", metric="EPE", claim_type="result")
    b = _claim(id=2, document_id=11, dataset="kitti", metric="epe", claim_type="result")
    score = _candidate_score(a, b)
    # same dataset (0.35) + same metric (0.25) + same type (0.2) + result-class (0.1) = 0.9
    assert score >= 0.85


def test_opposite_polarity_adds_boost():
    a = _claim(id=1, document_id=10, dataset="KITTI", polarity="positive")
    b = _claim(id=2, document_id=11, dataset="KITTI", polarity="negative")
    assert _candidate_score(a, b) >= 0.55  # positive vs negative -> +0.2


def test_build_candidates_caps_at_max():
    # 80 cap is enforced. Build 200 obviously-strong pairs across 30 docs.
    claims = []
    for did in range(30):
        claims.append(_claim(id=did * 2, document_id=did, dataset="KITTI", metric="EPE", claim_type="result"))
        claims.append(_claim(id=did * 2 + 1, document_id=did, dataset="KITTI", metric="EPE", claim_type="result"))
    pairs = _build_candidates(claims)
    assert len(pairs) <= 80
    # All candidate pairs must be from different documents
    for a, b, _score in pairs:
        assert a.document_id != b.document_id
