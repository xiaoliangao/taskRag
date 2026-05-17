from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    ARXIV = "arxiv"
    HUGGINGFACE = "huggingface"
    GITHUB = "github"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    OPENALEX = "openalex"
    RSS = "rss"
    UPLOAD_PDF = "upload_pdf"
    UPLOAD_URL = "upload_url"


class CollectionTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    BACKFILL = "backfill"
    UPLOAD = "upload"
    KEYWORD_CHANGED = "keyword_changed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class DocumentParseStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationType(StrEnum):
    TASK_DONE = "task_done"
    TASK_FAILED = "task_failed"
    SYSTEM = "system"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChannelStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


CELERY_QUEUE_URGENT = "urgent"
CELERY_QUEUE_SCHEDULED = "scheduled"
CELERY_QUEUE_BACKFILL = "backfill"
CELERY_QUEUE_INTELLIGENCE = "intelligence"
