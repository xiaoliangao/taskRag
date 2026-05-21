"""Pkg-R guard: ensure the 6 chat modes are present and `mode_hint` resolves."""
from __future__ import annotations

from app.rag.chat_modes import CHAT_MODES, CHAT_MODE_SYSTEM_HINTS, mode_hint


def test_what_if_mode_is_registered():
    assert "what_if" in CHAT_MODES
    assert "what_if" in CHAT_MODE_SYSTEM_HINTS


def test_what_if_hint_distinguishes_counterfactual_reasoning():
    hint = mode_hint("what_if")
    assert hint  # non-empty
    # Mention the structural anchors so prompt tuning regressions are caught
    assert "反事实" in hint
    assert "如果" in hint


def test_unknown_mode_falls_back_to_default():
    assert mode_hint("nonexistent_mode") == CHAT_MODE_SYSTEM_HINTS["default"]
    assert mode_hint(None) == CHAT_MODE_SYSTEM_HINTS["default"]


def test_every_registered_mode_has_a_hint():
    for m in CHAT_MODES:
        assert m in CHAT_MODE_SYSTEM_HINTS, f"missing hint for mode {m}"
        assert CHAT_MODE_SYSTEM_HINTS[m].strip(), f"empty hint for {m}"
