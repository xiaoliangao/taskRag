from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Quiet some noisy libs
    for noisy in ("httpx", "httpcore", "uvicorn.access", "passlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
