"""Celery tasks for the research intelligence layer (briefings, pulses, paths, gaps)."""
from __future__ import annotations

import logging

from app.db.session import get_sync_sessionmaker
from app.services.briefing_service import generate_document_briefing, generate_topic_document_insight
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.intel_tasks.generate_document_briefing_task")
def generate_document_briefing_task(document_id: int, language: str = "zh-CN") -> dict:
    Session = get_sync_sessionmaker()
    with Session() as db:
        b = generate_document_briefing(db, document_id, language)
        db.commit()
        return {"document_id": document_id, "status": b.status}


@celery_app.task(name="app.tasks.intel_tasks.generate_topic_document_insight_task")
def generate_topic_document_insight_task(topic_id: int, document_id: int) -> dict:
    Session = get_sync_sessionmaker()
    with Session() as db:
        generate_topic_document_insight(db, topic_id, document_id)
        db.commit()
        return {"topic_id": topic_id, "document_id": document_id}


@celery_app.task(name="app.tasks.intel_tasks.generate_topic_pulse_task")
def generate_topic_pulse_task(topic_id: int, force: bool = False) -> dict:
    from app.services.pulse_service import generate_topic_pulse

    Session = get_sync_sessionmaker()
    with Session() as db:
        p = generate_topic_pulse(db, topic_id, force=force)
        db.commit()
        return {"topic_id": topic_id, "status": p.status if p else "skipped"}


@celery_app.task(name="app.tasks.intel_tasks.generate_reading_path_task")
def generate_reading_path_task(topic_id: int) -> dict:
    from app.services.reading_path_service import generate_reading_path

    Session = get_sync_sessionmaker()
    with Session() as db:
        p = generate_reading_path(db, topic_id)
        db.commit()
        return {"topic_id": topic_id, "reading_path_id": p.id if p else None}


@celery_app.task(name="app.tasks.intel_tasks.generate_research_gaps_task")
def generate_research_gaps_task(topic_id: int) -> dict:
    from app.services.gap_service import generate_research_gaps

    Session = get_sync_sessionmaker()
    with Session() as db:
        ids = generate_research_gaps(db, topic_id)
        db.commit()
        return {"topic_id": topic_id, "created_insight_ids": ids}
