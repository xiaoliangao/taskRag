from __future__ import annotations

from app.rag.prompt import CONTEXT_CHAR_BUDGET, _allocate_budget, build_context_block


def test_allocate_budget_keeps_short_items_whole_and_redistributes():
    # short item fully kept, long item gets the leftover, total within budget.
    alloc = _allocate_budget([10, 10_000], budget=2000)
    assert alloc[0] == 10
    assert alloc[1] == 1990
    assert sum(alloc) <= 2000


def test_allocate_budget_never_exceeds_budget():
    lengths = [5000, 5000, 5000, 5000]
    alloc = _allocate_budget(lengths, budget=4000)
    assert sum(alloc) <= 4000
    assert all(a >= 0 for a in alloc)


def test_full_parent_survives_budget_unlike_old_800_cap():
    # A single ~2000-char parent must NOT be cut to 800 anymore.
    long_text = "x" * 2000
    block = build_context_block([{"title": "P", "url": "u", "text": long_text}])
    assert long_text in block  # full parent context preserved


def test_context_block_truncates_when_over_budget():
    texts = [{"title": str(i), "url": "u", "text": "y" * 20_000} for i in range(5)]
    block = build_context_block(texts, char_budget=5000)
    # 5 citations sharing 5000 chars → each ~1000, far below the 20k source.
    assert "…" in block  # truncation marker present
    body_chars = block.count("y")
    assert body_chars <= 5000


def test_default_budget_is_generous_enough_for_parent_swap():
    # Regression intent: budget should comfortably exceed the old 5*800=4000.
    assert CONTEXT_CHAR_BUDGET >= 8000
