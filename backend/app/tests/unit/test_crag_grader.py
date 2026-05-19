"""Unit tests for CRAG retrieval grader (v1.5 B-1)."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.crag import _format_candidates, grade_retrieval


def _cit(title: str, text: str = "snippet") -> SimpleNamespace:
    return SimpleNamespace(title=title, text=text)


def test_format_candidates_handles_empty():
    assert _format_candidates([]) == "(no candidates)"


def test_format_candidates_truncates_long_text():
    long_text = "x" * 1000
    out = _format_candidates([_cit("Paper A", long_text)])
    assert "Paper A" in out
    # Each candidate snippet is capped at 160 chars
    assert all(len(line) < 240 for line in out.split("\n"))


def test_grade_retrieval_empty_returns_low_verdict():
    # With no citations the grader short-circuits without calling the LLM.
    result = grade_retrieval("anything", [])
    assert result["verdict"] == "low"
    assert result["rewritten_query"] == "anything"
    assert "no candidates" in result["reason"]
