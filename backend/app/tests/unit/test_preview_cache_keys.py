"""Pkg-D guard: preview / discover cache keys are stable under input reorder
(otherwise we'd thrash the cache on the same logical query)."""
from __future__ import annotations

from app.services.discover_service import _discover_cache_key
from app.services.picker_service import _preview_cache_key


def test_preview_cache_key_independent_of_source_order():
    a = _preview_cache_key(7, ["arxiv", "openalex"], ["rag", "reranking"], 20)
    b = _preview_cache_key(7, ["openalex", "arxiv"], ["reranking", "rag"], 20)
    assert a == b


def test_preview_cache_key_changes_with_topic():
    a = _preview_cache_key(7, ["arxiv"], ["rag"], 20)
    b = _preview_cache_key(8, ["arxiv"], ["rag"], 20)
    assert a != b


def test_preview_cache_key_changes_with_limit():
    a = _preview_cache_key(7, ["arxiv"], ["rag"], 10)
    b = _preview_cache_key(7, ["arxiv"], ["rag"], 30)
    assert a != b


def test_discover_cache_key_has_no_topic_id():
    """Discover is topic-less; same sources+keywords ⇒ same key regardless of caller."""
    a = _discover_cache_key(["arxiv", "openalex"], ["x"], 20)
    b = _discover_cache_key(["openalex", "arxiv"], ["x"], 20)
    assert a == b
    # discover prefix differentiates from picker
    assert a.startswith("discover:v1:")
