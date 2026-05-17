from __future__ import annotations

from app.collectors.base import RawDocument, dedupe_raw_docs


def test_dedupe_by_source_external_id_keeps_first_and_collects_keywords():
    items = [
        RawDocument(source="arxiv", external_id="2401.00001", title="A", url="u", matched_keyword="rag"),
        RawDocument(source="arxiv", external_id="2401.00001", title="A", url="u", matched_keyword="reranker"),
        RawDocument(source="arxiv", external_id="2401.00002", title="B", url="u2", matched_keyword="rag"),
    ]
    out = dedupe_raw_docs(items)
    assert len(out) == 2
    first = next(d for d in out if d.external_id == "2401.00001")
    assert set(first.metadata.get("all_matched_keywords", [])) == {"rag", "reranker"}
    # matched_keyword stays as the first one
    assert first.matched_keyword == "rag"


def test_dedupe_empty_returns_empty():
    assert dedupe_raw_docs([]) == []
