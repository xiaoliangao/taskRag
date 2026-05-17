"""Reset demo user + topics. Destructive — only for local demo.

Usage:
    docker compose exec backend python scripts/reset_demo_data.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import get_sync_sessionmaker  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def reset() -> None:
    settings = get_settings()
    Session = get_sync_sessionmaker()
    with Session() as db:
        user = db.query(User).filter(User.email == settings.demo_user_email).first()
        if user:
            db.delete(user)
            db.commit()
            log.info("Deleted demo user and all owned topics/chats/tasks.")
        else:
            log.info("No demo user found.")


if __name__ == "__main__":
    reset()
