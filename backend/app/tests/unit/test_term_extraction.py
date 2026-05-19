"""Unit tests for app.services.term_extraction (Sprint 1 Trend Radar)."""
from __future__ import annotations

from app.services.term_extraction import (
    extract_candidates_for_document,
    normalize_term,
)


def test_normalize_term_lowercases_and_collapses_whitespace():
    assert normalize_term("  RAFT-Stereo   v2  ") == "raft-stereo v2"
    assert normalize_term("Vision\tLanguage\nModel") == "vision language model"


def test_extract_finds_camel_hyphen_acronyms_and_method_suffixes():
    cands = extract_candidates_for_document(
        title="RAFT-Stereo and LoRA improve Stereo Matching",
        abstract="Our work uses RAG with a custom transformer encoder.",
    )
    norms = {c.normalized for c in cands}
    # CamelCase-hyphen names
    assert "raft-stereo" in norms
    # All-caps acronyms
    assert "lora" in norms or "rag" in norms
    # method-suffix phrases ("stereo matching", "custom transformer")
    assert any("matching" in n for n in norms)


def test_extract_filters_stopwords_and_short_tokens():
    cands = extract_candidates_for_document(
        title="The method paper proposes a new model",
        abstract="",
    )
    norms = {c.normalized for c in cands}
    # generic stop words should not appear
    assert "the" not in norms
    assert "method" not in norms
    assert "paper" not in norms


def test_extract_datasets_field_emits_typed_candidates():
    cands = extract_candidates_for_document(
        title="A",
        abstract=None,
        briefing_datasets=["KITTI 2015", {"name": "Scene Flow"}],
    )
    by_norm = {c.normalized: c for c in cands}
    assert "kitti 2015" in by_norm
    assert by_norm["kitti 2015"].term_type == "dataset"
    assert by_norm["kitti 2015"].source_field == "datasets"
    assert "scene flow" in by_norm


def test_extract_dedups_within_same_source_field():
    cands = extract_candidates_for_document(
        title="RAG RAG RAG RAG",
        abstract=None,
    )
    rag_in_title = [c for c in cands if c.normalized == "rag" and c.source_field == "title"]
    # Each (norm, source_field) appears at most once.
    assert len(rag_in_title) <= 1
