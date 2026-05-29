from __future__ import annotations

from app.collectors.openalex_collector import _short_wid
from app.services.citation_graph_service import _recent_citations, compute_citation_pairs


def test_short_wid_strips_url():
    assert _short_wid("https://openalex.org/W2741809807") == "W2741809807"
    assert _short_wid("W123") == "W123"
    assert _short_wid(None) is None
    assert _short_wid("") is None


def test_compute_citation_pairs_resolves_intra_set_refs_only():
    nodes = [
        {"id": 1, "wid": "W1", "refs": ["W2", "https://openalex.org/W3", "W999"]},
        {"id": 2, "wid": "W2", "refs": []},
        {"id": 3, "wid": "W3", "refs": ["W1"]},
    ]
    pairs = set(compute_citation_pairs(nodes))
    # 1 cites 2 and 3 (W999 is outside the set → dropped); 3 cites 1.
    assert pairs == {(1, 2), (1, 3), (3, 1)}


def test_compute_citation_pairs_ignores_self_and_dups():
    nodes = [
        {"id": 1, "wid": "W1", "refs": ["W1", "W2", "W2"]},  # self + duplicate
        {"id": 2, "wid": "W2", "refs": []},
    ]
    assert compute_citation_pairs(nodes) == [(1, 2)]


def test_compute_citation_pairs_no_wid_no_edges():
    nodes = [
        {"id": 1, "wid": None, "refs": ["W2"]},
        {"id": 2, "wid": None, "refs": []},
    ]
    assert compute_citation_pairs(nodes) == []


def test_recent_citations_sums_two_latest_years():
    counts = [
        {"year": 2023, "cited_by_count": 5},
        {"year": 2025, "cited_by_count": 10},
        {"year": 2024, "cited_by_count": 7},
        {"year": 2020, "cited_by_count": 99},
    ]
    # two most recent reported years: 2025 (10) + 2024 (7) = 17
    assert _recent_citations(counts) == 17


def test_recent_citations_handles_empty_and_garbage():
    assert _recent_citations(None) == 0
    assert _recent_citations([]) == 0
    assert _recent_citations([{"nope": 1}]) == 0
