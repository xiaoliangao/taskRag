"""Celery tasks for v1.3+ research extensions (Trend Radar, Claims, Signals, etc.)."""
from __future__ import annotations

import logging

from app.db.models.document import Document, TopicDocument
from app.db.models.topic import Topic
from app.db.session import get_async_sessionmaker, get_sync_sessionmaker
from app.services.claim_service import ClaimService
from app.services.conflict_service import ConflictService
from app.services.signal_service import SignalService
from app.services.trend_service import TrendService
from app.tasks.celery_app import celery_app
from app.tasks.task_helpers import acquire_lock, make_lock_key, run_async

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


# --- v1.4 Sprint 1: async-bridge tasks for hypothesis / comparison / writing ---


@celery_app.task(name="app.tasks.research_tasks.verify_hypothesis_task")
def verify_hypothesis_task(check_id: int) -> dict:
    """Run a HypothesisCheck inside a fresh async session.

    The check row must already exist with status='pending'.
    """
    lock_key = make_lock_key("verify_hypothesis", check_id)
    with acquire_lock(lock_key, ttl=600) as got:
        if not got:
            log.info("verify_hypothesis_task skipped: lock held check_id=%s", check_id)
            return {"check_id": check_id, "status": "skipped_locked"}

        async def _run() -> dict:
            from app.db.models.research_ext import HypothesisCheck
            from app.services.hypothesis_service import HypothesisService

            SessionLocal = get_async_sessionmaker()
            async with SessionLocal() as db:
                check = await db.get(HypothesisCheck, check_id)
                if check is None:
                    return {"check_id": check_id, "status": "failed", "error": "check not found"}
                svc = HypothesisService(db)
                try:
                    await svc.run(check)
                except Exception as exc:  # pragma: no cover - inner service traces
                    log.exception("hypothesis_run_failed")
                    return {"check_id": check_id, "status": "failed", "error": str(exc)[:300]}
                await db.commit()
                return {
                    "check_id": check_id,
                    "status": check.status,
                    "verdict": check.verdict,
                    "confidence": check.confidence,
                }

        return run_async(_run)


@celery_app.task(name="app.tasks.research_tasks.run_method_comparison_task")
def run_method_comparison_task(session_id: int) -> dict:
    """Generate a method comparison matrix for an existing session row."""
    lock_key = make_lock_key("run_method_comparison", session_id)
    with acquire_lock(lock_key, ttl=600) as got:
        if not got:
            return {"session_id": session_id, "status": "skipped_locked"}

        async def _run() -> dict:
            from app.db.models.research_ext import ComparisonSession
            from app.services.comparison_service import ComparisonService

            SessionLocal = get_async_sessionmaker()
            async with SessionLocal() as db:
                row = await db.get(ComparisonSession, session_id)
                if row is None:
                    return {"session_id": session_id, "status": "failed", "error": "session not found"}
                svc = ComparisonService(db)
                try:
                    await svc.generate(row)
                except Exception as exc:
                    log.exception("comparison_generate_failed")
                    return {"session_id": session_id, "status": "failed", "error": str(exc)[:300]}
                await db.commit()
                return {"session_id": session_id, "status": row.status}

        return run_async(_run)


@celery_app.task(name="app.tasks.research_tasks.generate_writing_outline_task")
def generate_writing_outline_task(project_id: int) -> dict:
    """Generate an outline for a WritingProject (writing_type=related_work)."""
    lock_key = make_lock_key("generate_writing_outline", project_id)
    with acquire_lock(lock_key, ttl=600) as got:
        if not got:
            return {"project_id": project_id, "status": "skipped_locked"}

        async def _run() -> dict:
            from app.db.models.research_ext import WritingProject
            from app.services.writing_service import WritingService

            SessionLocal = get_async_sessionmaker()
            async with SessionLocal() as db:
                proj = await db.get(WritingProject, project_id)
                if proj is None:
                    return {"project_id": project_id, "status": "failed", "error": "project not found"}
                svc = WritingService(db)
                try:
                    await svc.generate_outline(proj)
                except Exception as exc:
                    log.exception("outline_generate_failed")
                    return {"project_id": project_id, "status": "failed", "error": str(exc)[:300]}
                await db.commit()
                return {"project_id": project_id, "status": proj.status}

        return run_async(_run)


@celery_app.task(name="app.tasks.research_tasks.rebuild_method_timeline_task")
def rebuild_method_timeline_task(topic_id: int, extract_edges: bool = True) -> dict:
    """Refresh method entities + optionally derive LLM evolution edges (v1.5 A-3)."""
    lock_key = make_lock_key("rebuild_method_timeline", topic_id)
    with acquire_lock(lock_key, ttl=600) as got:
        if not got:
            return {"topic_id": topic_id, "status": "skipped_locked"}
        Session = get_sync_sessionmaker()
        with Session() as db:
            topic = db.query(Topic).filter(Topic.id == topic_id).first()
            if not topic:
                return {"topic_id": topic_id, "status": "failed", "error": "topic not found"}
            from app.services.method_timeline_service import (
                extract_evolution_edges,
                rebuild_method_entities,
            )

            try:
                inserted = rebuild_method_entities(db, topic_id)
                edges = 0
                if extract_edges:
                    edges = extract_evolution_edges(db, topic_id, topic.name)
            except Exception as exc:
                log.exception("method_timeline_failed")
                db.commit()
                return {"topic_id": topic_id, "status": "failed", "error": str(exc)[:300]}
            db.commit()
            return {
                "topic_id": topic_id,
                "status": "success",
                "methods_inserted": inserted,
                "edges": edges,
            }


@celery_app.task(name="app.tasks.research_tasks.summarize_chat_session_task")
def summarize_chat_session_task(session_id: int) -> dict:
    """Generate/refresh a conversation summary (v1.4 Sprint 7 Memory).

    Skips silently if the session has too few new messages — `needs_resummary`
    is checked inside the task to avoid races between API + worker.
    """
    lock_key = make_lock_key("summarize_chat_session", session_id)
    with acquire_lock(lock_key, ttl=300) as got:
        if not got:
            return {"session_id": session_id, "status": "skipped_locked"}

        async def _run() -> dict:
            from app.services.memory_service import needs_resummary, summarize_session

            SessionLocal = get_async_sessionmaker()
            async with SessionLocal() as db:
                if not await needs_resummary(db, session_id):
                    return {"session_id": session_id, "status": "skipped_no_change"}
                summary = await summarize_session(db, session_id)
                await db.commit()
                if summary is None:
                    return {"session_id": session_id, "status": "skipped_too_short"}
                return {
                    "session_id": session_id,
                    "status": "success",
                    "summary_id": summary.id,
                    "memory_items": len(summary.memory_items_json or []),
                }

        return run_async(_run)


@celery_app.task(name="app.tasks.research_tasks.generate_writing_draft_task")
def generate_writing_draft_task(project_id: int) -> dict:
    """Generate a full draft (outline auto-fills if missing)."""
    lock_key = make_lock_key("generate_writing_draft", project_id)
    with acquire_lock(lock_key, ttl=900) as got:
        if not got:
            return {"project_id": project_id, "status": "skipped_locked"}

        async def _run() -> dict:
            from app.db.models.research_ext import WritingProject
            from app.services.writing_service import WritingService

            SessionLocal = get_async_sessionmaker()
            async with SessionLocal() as db:
                proj = await db.get(WritingProject, project_id)
                if proj is None:
                    return {"project_id": project_id, "status": "failed", "error": "project not found"}
                svc = WritingService(db)
                try:
                    await svc.generate_draft(proj)
                except Exception as exc:
                    log.exception("draft_generate_failed")
                    return {"project_id": project_id, "status": "failed", "error": str(exc)[:300]}
                await db.commit()
                return {"project_id": project_id, "status": proj.status}

        return run_async(_run)
