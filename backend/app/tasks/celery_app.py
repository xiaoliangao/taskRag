from __future__ import annotations

import time

from celery import Celery
from celery.schedules import schedule
from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    worker_process_init,
)

from app.core.config import get_settings
from app.core.constants import (
    CELERY_QUEUE_BACKFILL,
    CELERY_QUEUE_INTELLIGENCE,
    CELERY_QUEUE_SCHEDULED,
    CELERY_QUEUE_URGENT,
)

_settings = get_settings()
_task_start: dict[str, float] = {}

celery_app = Celery(
    "taskrag",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
    include=[
        "app.tasks.collect_tasks",
        "app.tasks.index_tasks",
        "app.tasks.notification_tasks",
        "app.tasks.schedule_tasks",
        "app.tasks.intel_tasks",
        "app.tasks.research_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    timezone="UTC",
    enable_utc=True,
    task_default_queue=CELERY_QUEUE_SCHEDULED,
    task_routes={
        "app.tasks.collect_tasks.collect_topic_source_task": {"queue": CELERY_QUEUE_SCHEDULED},
        "app.tasks.collect_tasks.backfill_topic_task": {"queue": CELERY_QUEUE_BACKFILL},
        "app.tasks.collect_tasks.ingest_picked_documents_task": {"queue": CELERY_QUEUE_URGENT},
        "app.tasks.notification_tasks.send_notification_task": {"queue": CELERY_QUEUE_URGENT},
        "app.tasks.schedule_tasks.enqueue_due_topic_sources_task": {"queue": CELERY_QUEUE_SCHEDULED},
        # Intelligence layer (v1.1+)
        "app.tasks.intel_tasks.generate_document_briefing_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.intel_tasks.generate_topic_document_insight_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.intel_tasks.generate_topic_pulse_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.intel_tasks.generate_reading_path_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.intel_tasks.generate_research_gaps_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        # v1.3+ research extensions
        "app.tasks.research_tasks.generate_topic_trend_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.research_tasks.refresh_topic_terms_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.research_tasks.extract_topic_claims_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.research_tasks.detect_topic_conflicts_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.research_tasks.refresh_topic_signals_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        # v1.4 Sprint 1: async-bridge tasks for hypothesis / comparison / writing
        "app.tasks.research_tasks.verify_hypothesis_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.research_tasks.run_method_comparison_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.research_tasks.generate_writing_outline_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.research_tasks.generate_writing_draft_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.research_tasks.summarize_chat_session_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
        "app.tasks.research_tasks.rebuild_method_timeline_task": {"queue": CELERY_QUEUE_INTELLIGENCE},
    },
    beat_schedule={
        "scan-due-topics": {
            "task": "app.tasks.schedule_tasks.enqueue_due_topic_sources_task",
            "schedule": schedule(60.0),
        },
        "scan-daily-pulses": {
            # Cheap idempotent check: emits at most one pulse per topic per day.
            "task": "app.tasks.schedule_tasks.enqueue_daily_pulses_task",
            "schedule": schedule(900.0),
        },
    },
    broker_connection_retry_on_startup=True,
)


# ---- Observability hooks (v1.4) ----


@worker_process_init.connect
def _init_observability_in_worker(**_: object) -> None:
    """Each Celery worker process needs its own init (Sentry + Prometheus)."""
    try:
        from app.core.observability import init_observability

        init_observability()
    except Exception:  # pragma: no cover - observability must never crash workers
        pass


@task_prerun.connect
def _task_prerun(task_id: str, task=None, **_: object) -> None:  # type: ignore[no-untyped-def]
    _task_start[task_id] = time.monotonic()


@task_postrun.connect
def _task_postrun(task_id: str, task=None, state: str = "SUCCESS", **_: object) -> None:  # type: ignore[no-untyped-def]
    started = _task_start.pop(task_id, None)
    if task is None:
        return
    name = task.name
    try:
        from app.core.observability import (
            intel_task_duration_seconds,
            intel_task_total,
        )

        if intel_task_total is not None:
            intel_task_total.labels(
                task=name, status=str(state).lower()
            ).inc()
        if started is not None and intel_task_duration_seconds is not None:
            intel_task_duration_seconds.labels(task=name).observe(time.monotonic() - started)
    except Exception:  # pragma: no cover
        pass


@task_failure.connect
def _task_failure(task_id: str, exception=None, **_: object) -> None:  # type: ignore[no-untyped-def]
    try:
        import sentry_sdk

        if exception is not None:
            sentry_sdk.capture_exception(exception)
    except Exception:  # pragma: no cover
        pass
