"""Unit tests for LLM cost estimation (Sprint 2 observability)."""
from __future__ import annotations

from decimal import Decimal

from app.core.observability import _estimate_cost


def test_known_model_returns_decimal_cost():
    cost = _estimate_cost("deepseek", "deepseek-chat", 1000, 1000)
    assert isinstance(cost, Decimal)
    assert cost > Decimal("0")
    # 1k in @ $0.00014 + 1k out @ $0.00028 = $0.00042
    assert abs(cost - Decimal("0.000420")) < Decimal("0.000010")


def test_unknown_model_returns_none():
    assert _estimate_cost("zzz", "unknown-model", 1000, 1000) is None


def test_zero_tokens_zero_cost():
    cost = _estimate_cost("deepseek", "deepseek-chat", 0, 0)
    assert cost == Decimal("0.000000")


def test_provider_model_match_is_case_insensitive():
    a = _estimate_cost("DeepSeek", "DeepSeek-Chat", 500, 500)
    b = _estimate_cost("deepseek", "deepseek-chat", 500, 500)
    assert a == b
