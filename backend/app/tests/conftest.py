"""Shared pytest fixtures.

For DB-backed tests we expect a Postgres at $SYNC_DATABASE_URL (set in CI).
Pure-function tests don't need this — they import directly.
"""
from __future__ import annotations

import os

import pytest

# Ensure JWT secret is set so importing app.main / Settings doesn't crash in CI.
os.environ.setdefault("JWT_SECRET_KEY", "ci-test-secret-key-min-32-chars-long-xx")
os.environ.setdefault("APP_ENV", "development")


@pytest.fixture
def fake_document_id() -> int:
    return 999


@pytest.fixture
def fake_topic_id() -> int:
    return 1
