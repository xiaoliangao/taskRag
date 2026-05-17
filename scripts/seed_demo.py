"""Seed a demo user and 3 starter topics.

Usage:
    docker compose exec backend python scripts/seed_demo.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.models.topic import Topic, TopicSourceState  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import get_sync_sessionmaker  # noqa: E402
from app.indexer.qdrant_client import ensure_collection  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


DEFAULT_USER_SETTINGS = {
    "timezone": "Asia/Singapore",
    "email_notifications_enabled": True,
    "preferred_llm_provider": "deepseek",
    "preferred_llm_model": "deepseek-chat",
    "preferred_embedding_provider": "siliconflow",
}

PRESET_TOPICS = [
    {
        "name": "Stereo Matching",
        "description": "Tracking stereo matching / disparity estimation papers.",
        "keywords": ["stereo matching", "transformer stereo", "depth estimation"],
        "sources": ["arxiv"],
    },
    {
        "name": "RAG",
        "description": "Retrieval Augmented Generation research.",
        "keywords": ["retrieval augmented generation", "RAG", "reranking"],
        "sources": ["arxiv"],
    },
    {
        "name": "Diffusion Models",
        "description": "Diffusion models for image/video generation.",
        "keywords": ["diffusion model", "text to image", "denoising diffusion"],
        "sources": ["arxiv"],
    },
]


def seed() -> None:
    settings = get_settings()
    try:
        ensure_collection()
        log.info("Qdrant collection ready")
    except Exception as exc:
        log.warning("Qdrant ensure_collection failed (will retry at runtime): %s", exc)

    Session = get_sync_sessionmaker()
    with Session() as db:
        email = settings.demo_user_email.lower().strip()
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                password_hash=hash_password(settings.demo_user_password),
                settings_json=dict(DEFAULT_USER_SETTINGS),
            )
            db.add(user)
            db.flush()
            log.info("Created demo user %s", email)
        else:
            log.info("Demo user already exists: id=%s", user.id)

        for spec in PRESET_TOPICS:
            existing = (
                db.query(Topic)
                .filter(Topic.user_id == user.id, Topic.name == spec["name"])
                .first()
            )
            if existing:
                log.info("Topic '%s' already exists (id=%s)", existing.name, existing.id)
                continue
            t = Topic(
                user_id=user.id,
                name=spec["name"],
                description=spec["description"],
                keywords=spec["keywords"],
                sources=spec["sources"],
                schedule_type="daily",
                schedule_time="09:00",
                max_results_per_source_per_run=10,
                enabled=True,
            )
            db.add(t)
            db.flush()
            for src in spec["sources"]:
                db.add(TopicSourceState(topic_id=t.id, source=src))
            log.info("Created topic '%s' (id=%s)", t.name, t.id)

        db.commit()

    log.info("Seed complete.")
    log.info("Login at http://localhost:5173 with %s / %s", email, settings.demo_user_password)


if __name__ == "__main__":
    seed()
