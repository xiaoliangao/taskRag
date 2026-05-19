"""Unit tests for the citation validator (Sprint 4 Related Work Studio)."""
from __future__ import annotations

from app.services.writing_service import validate_citations


def test_clean_draft_with_matching_citations():
    draft = "RAG benefits from reranking [1]. Hybrid search complements vectors [2]."
    citations = [
        {"label": "[1]", "document_id": 101},
        {"label": "[2]", "document_id": 102},
    ]
    errors = validate_citations(draft, citations, {101, 102})
    assert errors == []


def test_citation_label_missing_from_json():
    draft = "Foo [1]. Bar [2]."
    citations = [{"label": "[1]", "document_id": 101}]  # missing [2]
    errors = validate_citations(draft, citations, {101})
    assert any("[2]" in e for e in errors)


def test_citation_points_to_disallowed_document():
    draft = "Quux [3]."
    citations = [{"label": "[3]", "document_id": 999}]  # not in allowed set
    errors = validate_citations(draft, citations, {101, 102})
    assert any("999" in e for e in errors)


def test_empty_draft_or_no_citations_used_passes():
    assert validate_citations("", [], set()) == []
    # Draft has no [N] tokens used → nothing to validate
    assert validate_citations("Plain prose without refs.", [], {101}) == []


def test_unused_extra_citation_does_not_fail():
    # Extra citation entries not referenced in draft are fine (informational sidebar)
    draft = "Only refs [1]."
    citations = [
        {"label": "[1]", "document_id": 101},
        {"label": "[2]", "document_id": 102},  # extra, OK
    ]
    assert validate_citations(draft, citations, {101, 102}) == []
