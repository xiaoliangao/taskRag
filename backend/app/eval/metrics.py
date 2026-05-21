"""Retrieval metrics for the eval suite.

We compute three structural metrics (no LLM judge in this MVP):
- Recall@K — fraction of expected chunks that appear in the top-K results
- MRR    — mean reciprocal rank of the first relevant chunk

Faithfulness / answer relevance via LLM judge is deferred — they cost a
second LLM call per question and risk circular validation. Structural
metrics are deterministic and reproducible.
"""
from __future__ import annotations

from collections.abc import Iterable


def recall_at_k(retrieved_ids: list[int], expected_ids: list[int], k: int) -> float:
    """Fraction of expected ids that appear in the first K retrieved ids.
    Returns 0.0 if expected_ids is empty (treats as no signal rather than 1.0)."""
    expected = set(expected_ids or [])
    if not expected:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & expected) / len(expected)


def reciprocal_rank(retrieved_ids: list[int], expected_ids: list[int]) -> float:
    """1 / (rank of first relevant chunk), 1-indexed. 0 if none of the
    expected chunks appear in the retrieved list."""
    expected = set(expected_ids or [])
    if not expected:
        return 0.0
    for i, cid in enumerate(retrieved_ids, start=1):
        if cid in expected:
            return 1.0 / i
    return 0.0


def aggregate(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)
