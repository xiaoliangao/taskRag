"""Celery tasks for v1.3+ research extensions (Trend Radar, Claims, Signals)."""
from __future__ import annotations

import logging

from app.db.models.document import Document, TopicDocument
from app.db.models.topic import Topic
from app.db.session import get_sync_sessionmaker
from app.services.claim_service import ClaimService
from app.services.conflict_service import ConflictService
from app.services.signal_service import SignalService
from app.services.trend_service import TrendService
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.research_tasks.generate_topic_trend_task")
def generate_topic_trend_task(topic_id: int, window_days: int = 60) -> dict:
    Session = get_sync_sessionmaker()
    with Session() as db:
        service = TrendService(db)
        service.rebuild_terms_for_topic(topic_id)
        try:
            run_id = service.generate_trend_run(topic_id, window_days=window_days)
        except Exception as exc:  # pragma: no cover - error path traced inside service
            db.commit()
            return {"topic_id": topic_id, "status": "failed", "error": str(exc)}
        db.commit()
        return {"topic_id": topic_id, "trend_run_id": run_id, "status": "success"}


@celery_app.task(name="app.tasks.research_tasks.refresh_topic_terms_task")
def refresh_topic_terms_task(topic_id: int) -> dict:
    Session = get_sync_sessionmaker()
    with Session() as db:
        service = TrendService(db)
        count = service.rebuild_terms_for_topic(topic_id)
        db.commit()
        return {"topic_id": topic_id, "occurrences": count, "status": "success"}


@celery_app.task(name="app.tasks.research_tasks.extract_topic_claims_task")
def extract_topic_claims_task(topic_id: int, limit_docs: int = 30) -> dict:
    Session = get_sync_sessionmaker()
    with Session() as db:
        service = ClaimService(db)
        try:
            stats = service.extract_for_topic(topic_id, limit_docs=limit_docs)
        except Exception as exc:
            log.exception("claim_extract_failed")
            db.commit()
            return {"topic_id": topic_id, "status": "failed", "error": str(exc)}
        db.commit()
        return {"topic_id": topic_id, "status": "success", **stats}


@celery_app.task(name="app.tasks.research_tasks.detect_topic_conflicts_task")
def detect_topic_conflicts_task(topic_id: int, extract_first: bool = True) -> dict:
    Session = get_sync_sessionmaker()
    with Session() as db:
        if extract_first:
            ClaimService(db).extract_for_topic(topic_id, limit_docs=30)
            db.flush()
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        topic_name = topic.name if topic else ""
        doc_rows = (
            db.query(Document.id, Document.title)
            .join(TopicDocument, TopicDocument.document_id == Document.id)
            .filter(TopicDocument.topic_id == topic_id)
            .all()
        )
        title_lookup = {row.id: row.title for row in doc_rows}
        try:
            stats = ConflictService(db).detect_for_topic(
                topic_id, topic_name=topic_name, title_lookup=title_lookup
            )
        except Exception as exc:
            log.exception("conflict_detect_failed")
            db.commit()
            return {"topic_id": topic_id, "status": "failed", "error": str(exc)}
        db.commit()
        return {"topic_id": topic_id, "status": "success", **stats}


@celery_app.task(name="app.tasks.research_tasks.refresh_topic_signals_task")
def refresh_topic_signals_task(topic_id: int) -> dict:
    Session = get_sync_sessionmaker()
    with Session() as db:
        try:
            stats = SignalService(db).refresh_for_topic(topic_id)
        except Exception as exc:
            log.exception("signal_refresh_failed")
            db.commit()
            return {"topic_id": topic_id, "status": "failed", "error": str(exc)}
        db.commit()
        return {"topic_id": topic_id, "status": "success", **stats}
