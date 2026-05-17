"""Wait for postgres / redis / qdrant to be up before starting workers."""
from __future__ import annotations

import logging
import socket
import time
import urllib.parse
from typing import Iterable

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import get_settings  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _host_port(url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname or "localhost", parsed.port or 80


def _wait_one(label: str, host: str, port: int, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=3):
                log.info("%s up at %s:%d", label, host, port)
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"{label} not reachable at {host}:{port} after {timeout}s")


def wait_for_all() -> None:
    s = get_settings()
    targets: Iterable[tuple[str, str]] = (
        ("postgres", s.database_url.replace("postgresql+asyncpg", "postgresql").replace("postgresql+psycopg", "postgresql")),
        ("redis", s.redis_url),
        ("qdrant", s.qdrant_url),
    )
    for label, url in targets:
        host, port = _host_port(url if "://" in url else f"tcp://{url}")
        _wait_one(label, host, port)


if __name__ == "__main__":
    wait_for_all()
