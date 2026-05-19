from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TaskProgress(BaseModel):
    step: str | None = None  # searching / ingesting / done
    total: int | None = None
    processed: int | None = None
    current_doc: str | None = None
    current_title: str | None = None
    new: int | None = None
    reused: int | None = None
    skipped: int | None = None
    last_error: str | None = None


class TaskPublic(BaseModel):
    id: int
    topic_id: int
    source: str
    trigger: str
    status: str
    new_docs_count: int
    reused_docs_count: int
    skipped_docs_count: int
    started_at: datetime | None
    finished_at: datetime | None
    error_msg: str | None
    created_at: datetime
    progress: TaskProgress | None = None


class TaskListResponse(BaseModel):
    items: list[TaskPublic]
    total: int
