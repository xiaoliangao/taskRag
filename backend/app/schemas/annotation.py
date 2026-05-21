from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AnnotationRect(BaseModel):
    """A single rectangle in PDF page coordinates (origin bottom-left, points)."""

    x: float
    y: float
    w: float
    h: float


class AnnotationCreate(BaseModel):
    page_number: int = Field(ge=1)
    kind: Literal["highlight", "comment", "note"]
    color: str = Field(default="#fff59d", min_length=4, max_length=24)
    selected_text: str = Field(min_length=1, max_length=8000)
    rects: list[AnnotationRect] = Field(min_length=1, max_length=200)
    comment_md: str | None = Field(default=None, max_length=20_000)
    # If True, also insert a research_notes row referencing this annotation.
    save_as_note: bool = False


class AnnotationPatch(BaseModel):
    color: str | None = Field(default=None, min_length=4, max_length=24)
    kind: Literal["highlight", "comment", "note"] | None = None
    comment_md: str | None = Field(default=None, max_length=20_000)


class AnnotationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    topic_id: int
    chunk_id: int | None
    page_number: int
    kind: str
    color: str
    selected_text: str
    rects: list[dict[str, Any]]
    comment_md: str | None
    note_id: int | None
    created_at: datetime
    updated_at: datetime
