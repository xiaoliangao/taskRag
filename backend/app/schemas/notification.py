from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    body: str
    payload: dict
    read_at: datetime | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationPublic]
    total: int
    unread_count: int


class MarkAllReadResponse(BaseModel):
    updated_count: int
