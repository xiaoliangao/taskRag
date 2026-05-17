from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PreviewRequest(BaseModel):
    sources: list[str] | None = None    # subset of topic.sources; default all
    limit: int = Field(default=20, ge=1, le=50)


class PreviewItem(BaseModel):
    source: str
    external_id: str
    title: str
    authors: list[str] = []
    published_at: datetime | None = None
    url: str
    abstract: str | None = None
    raw_content_url: str | None = None
    matched_keyword: str | None = None
    metadata: dict[str, Any] = {}
    already_in_topic: bool = False        # if true, picking it will be a no-op


class PreviewResponse(BaseModel):
    sources_queried: list[str]
    rate_limited_sources: list[str] = []
    items: list[PreviewItem]


class CollectSelectedRequest(BaseModel):
    picks: list[PreviewItem] = Field(min_length=1, max_length=50)


class CollectSelectedResponse(BaseModel):
    task_id: int
    count: int
    status: str  # queued
