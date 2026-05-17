"""Shared LLM JSON parsing helpers (Sprint 0)."""
from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from an LLM response.

    Tolerates markdown code fences, surrounding chatter, and lone-object output.
    """
    if not text:
        raise ValueError("Empty LLM response")
    cleaned = text.strip()
    # Strip ```json ... ``` fences
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, count=1).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")
    return data


def safe_parse_json_object(
    text: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return extract_json_object(text)
    except Exception:
        return dict(fallback or {})


def normalize_confidence(value: Any, default: float = 0.5) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v < 0:
        return 0.0
    if v > 1:
        return 1.0
    return v


def truncate_for_llm(text: str, max_chars: int = 12000) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 32] + "\n…[truncated]"
