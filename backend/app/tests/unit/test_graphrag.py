"""Unit tests for GraphRAG settings/feature flag (v1.5 B-2)."""
from __future__ import annotations

from app.core.config import get_settings


def test_graphrag_feature_flag_present_and_defaults_on():
    s = get_settings()
    assert hasattr(s, "graphrag_enabled")
    # Default state in dev: on (can be flipped via env GRAPHRAG_ENABLED=false)
    assert s.graphrag_enabled is True


def test_crag_feature_flag_present_and_defaults_on():
    s = get_settings()
    assert hasattr(s, "crag_enabled")
    assert s.crag_enabled is True
