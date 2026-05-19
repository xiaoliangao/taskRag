from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.core.constants import CollectionTrigger
from app.db.models.topic import Topic, TopicSourceState
from app.db.session import get_sync_sessionmaker
from app.tasks.celery_app import celery_app
from app.tasks.collect_tasks import collect_topic_source_task

log = logging.getLogger(__name__)


def _is_due(topic: Topic, state: TopicSourceState | None, now: datetime) -> bool:
    if state is None or state.last_success_at is None:
        return True  # never fetched
    elapsed = now - state.last_success_at
    if topic.schedule_type == "weekly":
        return elapsed >= timedelta(days=7)
    return elapsed >= timedelta(hours=24) - timedelta(minutes=5)


@celery_app.task(name="app.tasks.schedule_tasks.enqueue_due_topic_sources_task")
def enqueue_due_topic_sources_task() -> dict:
    Session = get_sync_sessionmaker()
    now = datetime.now(tz=UTC)
    enqueued: list[dict] = []
    with Session() as db:
        topics = db.query(Topic).filter(Topic.enabled.is_(True)).all()
        for t in topics:
            for src in t.sources:
                state = (
                    db.query(TopicSourceState)
                    .filter(TopicSourceState.topic_id == t.id, TopicSourceState.source == src)
                    .first()
                )
                if not _is_due(t, state, now):
                    continue
                collect_topic_source_task.apply_async(
                    kwargs=dict(
                        topic_id=t.id,
                        source=src,
                        trigger=CollectionTrigger.SCHEDULED.value,
                    ),
                    queue="scheduled",
                )
                enqueued.append({"topic_id": t.id, "source": src})
    if enqueued:
        log.info("enqueued %d due collection tasks", len(enqueued))
    return {"enqueued": enqueued}


@celery_app.task(name="app.tasks.schedule_tasks.enqueue_daily_pulses_task")
def enqueue_daily_pulses_task() -> dict:
    """Enqueue a Pulse generation for each active Topic, once per day per topic."""
    from app.db.models.intel import TopicPulse
    from app.services.pulse_service import _today_utc_date
    from app.tasks.intel_tasks import generate_topic_pulse_task

    Session = get_sync_sessionmaker()
    today = _today_utc_date()
    enqueued: list[int] = []
    with Session() as db:
        topics = db.query(Topic).filter(Topic.enabled.is_(True)).all()
        for t in topics:
            existing = (
                db.query(TopicPulse)
                .filter(TopicPulse.topic_id == t.id, TopicPulse.pulse_date == today)
                .first()
            )
            if existing and existing.status == "success":
                continue
            generate_topic_pulse_task.apply_async(
                kwargs=dict(topic_id=t.id, force=False), queue="intelligence"
            )
            enqueued.append(t.id)
    return {"enqueued_topic_ids": enqueued}
