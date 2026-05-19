"""Unit tests for hypothesis verdict aggregation."""
from __future__ import annotations

from app.services.hypothesis_service import _aggregate_verdict


def test_no_evidence_is_insufficient():
    assert _aggregate_verdict([]) == "insufficient"


def test_clear_majority_support_is_supported():
    assert _aggregate_verdict(["support", "support", "support"]) == "supported"
    # 2x support + 1x neutral still passes the 2*opp threshold
    assert _aggregate_verdict(["support", "support", "neutral"]) == "supported"


def test_clear_majority_oppose_is_refuted():
    assert _aggregate_verdict(["oppose", "oppose", "oppose"]) == "refuted"


def test_mixed_is_mixed():
    # 2 support, 2 oppose -> neither side dominates
    assert _aggregate_verdict(["support", "support", "oppose", "oppose"]) == "mixed"


def test_only_qualify_is_qualified():
    assert _aggregate_verdict(["qualify", "qualify", "qualify"]) == "qualified"


def test_only_one_evidence_is_insufficient():
    # one support + nothing else - not enough signal yet
    assert _aggregate_verdict(["support"]) == "insufficient"
