from __future__ import annotations

from celery import Celery
from celery.schedules import schedule

from app.core.config import get_settings
from app.core.constants import (
    CELERY_QUEUE_BACKFILL,
    CELERY_QUEUE_INTELLIGENCE,
    CELERY_QUEUE_SCHEDULED,
    CELERY_QUEUE_URGENT,
)

_settings = get_settings()

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
