"""Shared helpers for Celery tasks: idempotency locks, async-bridge, error envelope."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

import redis

from app.core.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T")

_LOCK_DEFAULT_TTL = 300  # seconds


def _redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def make_lock_key(task_name: str, *parts: Any) -> str:
    """Stable lock key from task name + arbitrary scope parts."""
    payload = json.dumps([task_name, *parts], sort_keys=True, default=str)
    digest = hashlib.md5(payload.encode()).hexdigest()[:16]
    return f"intel:lock:{task_name}:{digest}"


@contextmanager
def acquire_lock(key: str, *, ttl: int = _LOCK_DEFAULT_TTL) -> Iterator[bool]:
    """Acquire a Redis SETNX lock. Yields True if acquired, False if already held.

    Caller is responsible for skipping when lock is False.
    """
    client = _redis_client()
    acquired = bool(client.set(key, "1", nx=True, ex=ttl))
    try:
        yield acquired
    finally:
        if acquired:
            try:
                client.delete(key)
            except Exception:  # pragma: no cover - best-effort cleanup
                log.warning("failed to release lock %s", key)


def run_async(coro_factory: Callable[[], Awaitable[T]]) -> T:
    """Run an async coroutine in the current Celery sync worker.

    `coro_factory` must be a zero-arg callable returning a fresh coroutine —
    this avoids "coroutine reused" errors if Celery retries.
    """
    return asyncio.run(coro_factory())


__all__ = ["make_lock_key", "acquire_lock", "run_async"]
