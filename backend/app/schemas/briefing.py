from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BriefingPublic(BaseModel):
    status: str
    language: str
    one_sentence_summary: str | None = None
    problem: str | None = None
    method: str | None = None
    contributions: list = []
    experiments: list = []
    limitations: list = []
    datasets: list = []
    metrics: list = []
    code_available: bool | None = None
    code_url: str | None = None
    reading_time_minutes: int | None = None
    evidence_chunk_ids: list = []
    generated_at: datetime | None = None


class TopicInsightPublic(BaseModel):
    relevance_score: float | None = None
    relevance_reason: str | None = None
    reading_priority: str | None = None
    why_read: str | None = None
    tags: list = []


class UserDocStatePublic(BaseModel):
    status: str = "unread"
    favorite: bool = False
    rating: int | None = None
    personal_note: str | None = None
    tags: list = []
    last_opened_at: datetime | None = None


class UserDocStateUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(unread|reading|read|archived)$")
    favorite: bool | None = None
    rating: int | None = Field(default=None, ge=0, le=5)
    personal_note: str | None = None
    tags: list | None = None


class DocumentBriefingResponse(BaseModel):
    document_id: int
    title: str
    briefing: BriefingPublic | None
    topic_insight: TopicInsightPublic | None
    user_state: UserDocStatePublic | None


class BriefingGenerateResponse(BaseModel):
    document_id: int
    status: str  # queued / success
    message: str | None = None
