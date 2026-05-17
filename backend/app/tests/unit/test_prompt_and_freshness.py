from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.rag.prompt import NO_CONTEXT_FALLBACK, build_context_block, build_messages
from app.rag.retriever import _freshness


def test_no_context_fallback_is_non_empty():
    assert NO_CONTEXT_FALLBACK.strip()


def test_build_messages_contains_question_and_citations():
    citations = [
        {"title": "T1", "url": "https://x/1", "published_at": "2026-01-01", "section_title": "Intro", "text": "abc"},
    ]
    msgs = build_messages(question="hello?", chat_history=[], citations=citations)
    assert msgs[0]["role"] == "system"
    assert "hello?" in msgs[-1]["content"]
    assert "T1" in msgs[-1]["content"]


def test_freshness_decay_monotonic():
    now = datetime(2026, 5, 15, tzinfo=timezone.utc)
    recent = _freshness(now - timedelta(days=1), now)
    older = _freshness(now - timedelta(days=365), now)
    older2 = _freshness(now - timedelta(days=730), now)
    assert recent > older > older2 > 0
    assert _freshness(None, now) == 0.5


def test_context_block_renders_each_citation():
    block = build_context_block(
        [
            {"title": "A", "url": "u1", "published_at": "2026-01-01", "text": "alpha"},
            {"title": "B", "url": "u2", "published_at": "2026-02-01", "text": "beta"},
        ]
    )
    assert "[1]" in block and "[2]" in block
    assert "alpha" in block and "beta" in block
