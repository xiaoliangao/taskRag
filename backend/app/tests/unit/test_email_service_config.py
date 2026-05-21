"""Pkg-auth guard: `is_configured()` reflects env, and `send_email` rejects
the unconfigured case before touching the network."""
from __future__ import annotations

import pytest

from app.core import config as config_module
from app.services import email_service


def _make_settings(**over) -> object:
    """Build a Settings instance with required JWT key plus any overrides."""
    return config_module.Settings(
        jwt_secret_key="ci-test-secret-key-min-32-chars-long-xx",
        **over,
    )


def test_is_configured_false_when_creds_missing(monkeypatch):
    monkeypatch.setattr(
        email_service, "get_settings", lambda: _make_settings(gmail_username="", email_from="")
    )
    assert email_service.is_configured() is False


def test_is_configured_true_when_all_three_set(monkeypatch):
    s = _make_settings(
        gmail_username="x@example.com",
        gmail_app_password="abcd" * 4,
        email_from="x@example.com",
    )
    monkeypatch.setattr(email_service, "get_settings", lambda: s)
    assert email_service.is_configured() is True


def test_send_email_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(
        email_service, "get_settings", lambda: _make_settings(gmail_username="")
    )
    with pytest.raises(email_service.EmailNotConfiguredError):
        email_service.send_email(
            to="y@example.com",
            subject="t",
            text_body="t",
        )
