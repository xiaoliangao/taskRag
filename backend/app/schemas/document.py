from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    id: int
    source: str
    title: str
    authors: list[str] = []
    published_at: datetime | None = None
    url: str
    abstract: str | None = None
    matched_keyword: str | None = None
    added_at: datetime
    reading_priority: str | None = None  # high / medium / low / unknown
    relevance_score: float | None = None
    # True when ingestion only captured the abstract (no full PDF retrievable).
    # Lets the UI flag shallow RAG coverage on a row-by-row basis.
    abstract_only: bool | None = None


class DocumentChunkPublic(BaseModel):
    id: int
    chunk_index: int
    section_title: str | None
    page_start: int | None
    page_end: int | None
    text: str


class DocumentDetail(BaseModel):
    id: int
    source: str
    title: str
    authors: list[str] = []
    published_at: datetime | None = None
    url: str
    abstract: str | None = None
    full_text: str | None = None
    chunks: list[DocumentChunkPublic] = []
    abstract_only: bool | None = None
    favorite: bool = False  # per-current-user star state


class DocumentListResponse(BaseModel):
    items: list[DocumentSummary]
    page: int
    page_size: int
    total: int


class UploadResponse(BaseModel):
    task_id: int | None = None
    status: str
    message: str | None = None
