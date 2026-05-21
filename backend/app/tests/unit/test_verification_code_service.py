"""Pkg-auth guard: verification-code rate limit + daily cap + consume.

We don't need a real Redis — a tiny in-memory fake covers the TTL semantics
we care about (SETEX, GET, DELETE, INCR, EXPIRE, TTL)."""
from __future__ import annotations

import time

import pytest

from app.core.errors import RateLimitedError, ValidationError
from app.services import verification_code_service as vcs


class FakeRedis:
    """Just enough Redis to test rate-limit / daily-cap / verify-consume."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, float | None]] = {}

    def _expired(self, key: str) -> bool:
        v = self.store.get(key)
        if v is None:
            return True
        _, exp = v
        return exp is not None and exp <= time.time()

    def get(self, key: str):
        if self._expired(key):
            self.store.pop(key, None)
            return None
        return self.store[key][0]

    def setex(self, key: str, ttl: int, value: str):
        self.store[key] = (value, time.time() + ttl)

    def delete(self, key: str):
        self.store.pop(key, None)

    def ttl(self, key: str) -> int:
        if self._expired(key):
            self.store.pop(key, None)
            return -2
        _, exp = self.store[key]
        return int(exp - time.time()) if exp else -1

    def incr(self, key: str) -> int:
        if self._expired(key):
            self.store[key] = ("1", None)
            return 1
        val, exp = self.store[key]
        n = int(val) + 1
        self.store[key] = (str(n), exp)
        return n

    def expire(self, key: str, ttl: int) -> None:
        v = self.store.get(key)
        if v is None:
            return
        val, _ = v
        self.store[key] = (val, time.time() + ttl)


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    r = FakeRedis()
    monkeypatch.setattr(vcs, "_redis", lambda: r)
    return r


@pytest.fixture
def mute_smtp(monkeypatch):
    """Force the "SMTP not configured" path so tests never try to send mail."""
    monkeypatch.setattr(vcs, "is_configured", lambda: False)


def test_first_send_succeeds_and_drops_to_log_when_smtp_unset(fake_redis, mute_smtp):
    r = vcs.generate_and_send_code("user@example.com")
    assert r.delivery == "log"
    assert r.cooldown_s == vcs.COOLDOWN_S
    # Code should be stored under TTL
    code = fake_redis.get("auth:vcode:code:user@example.com")
    assert code is not None
    assert code.isdigit() and len(code) == 6


def test_second_send_within_cooldown_is_rate_limited(fake_redis, mute_smtp):
    vcs.generate_and_send_code("user@example.com")
    with pytest.raises(RateLimitedError):
        vcs.generate_and_send_code("user@example.com")


def test_daily_cap_blocks_after_n_sends(fake_redis, mute_smtp):
    email = "capped@example.com"
    for _ in range(vcs.DAILY_LIMIT):
        # Bypass cooldown between attempts so we can probe the daily cap.
        vcs.generate_and_send_code(email)
        fake_redis.delete(vcs._cooldown_key(email))
    with pytest.raises(RateLimitedError):
        vcs.generate_and_send_code(email)


def test_verify_and_consume_happy_path(fake_redis, mute_smtp):
    email = "ok@example.com"
    vcs.generate_and_send_code(email)
    code = fake_redis.get(vcs._code_key(email))
    vcs.verify_and_consume(email, code)
    # Consumed — second verify with same code must fail
    with pytest.raises(ValidationError):
        vcs.verify_and_consume(email, code)


def test_verify_wrong_code_rejected(fake_redis, mute_smtp):
    email = "wrong@example.com"
    vcs.generate_and_send_code(email)
    with pytest.raises(ValidationError):
        vcs.verify_and_consume(email, "000000")
    # Original code still in store; user can retry with right code.
    assert fake_redis.get(vcs._code_key(email)) is not None


def test_verify_unknown_email_rejected(fake_redis):
    with pytest.raises(ValidationError):
        vcs.verify_and_consume("never-sent@example.com", "123456")
