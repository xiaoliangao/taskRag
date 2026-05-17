from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    keywords: list[str] = Field(min_length=1, max_length=10)
    sources: list[str] = Field(min_length=1, max_length=10)
    schedule_type: Literal["daily", "weekly"] = "daily"
    schedule_time: str = "09:00"
    max_results_per_source_per_run: int = Field(default=3, ge=1, le=50)
    enabled: bool = True

    @field_validator("keywords")
    @classmethod
    def _strip_keywords(cls, v: list[str]) -> list[str]:
        cleaned = [k.strip() for k in v if k and k.strip()]
        if not cleaned:
            raise ValueError("keywords must contain at least one non-empty string")
        if any(len(k) > 80 for k in cleaned):
            raise ValueError("each keyword must be <= 80 characters")
        return cleaned

    @field_validator("sources")
    @classmethod
    def _validate_sources(cls, v: list[str]) -> list[str]:
        from app.core.constants import SourceType

        allowed = {s.value for s in SourceType}
        cleaned = [s.strip() for s in v if s and s.strip()]
        bad = [s for s in cleaned if s not in allowed]
        if bad:
            raise ValueError(f"unsupported sources: {bad}")
        return cleaned


class TopicUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    keywords: list[str] | None = None
    sources: list[str] | None = None
    schedule_type: Literal["daily", "weekly"] | None = None
    schedule_time: str | None = None
    max_results_per_source_per_run: int | None = Field(default=None, ge=1, le=100)
    enabled: bool | None = None

    @field_validator("keywords")
    @classmethod
    def _keywords(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [k.strip() for k in v if k and k.strip()]
        if not cleaned:
            raise ValueError("keywords must contain at least one non-empty string")
        if len(cleaned) > 10:
            raise ValueError("at most 10 keywords")
        return cleaned

    @field_validator("sources")
    @classmethod
    def _sources(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        from app.core.constants import SourceType
        allowed = {s.value for s in SourceType}
        cleaned = [s.strip() for s in v if s and s.strip()]
        bad = [s for s in cleaned if s not in allowed]
        if bad:
            raise ValueError(f"unsupported sources: {bad}")
        return cleaned


class TopicPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    keywords: list[str]
    sources: list[str]
    schedule_type: str
    schedule_time: str
    max_results_per_source_per_run: int
    enabled: bool
    document_count: int = 0
    last_collected_at: datetime | None = None
    created_at: datetime


class CollectTriggerResponse(BaseModel):
    tasks: list[dict]
