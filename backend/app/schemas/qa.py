from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatSessionCreate(BaseModel):
    title: str = Field(default="New Chat", min_length=1, max_length=200)
    mode: str = Field(default="default", max_length=32)


class ChatSessionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    mode: str | None = Field(default=None, max_length=32)


class ChatSessionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int
    title: str
    mode: str = "default"
    created_at: datetime


class ChatMessagePublic(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    citations: list[dict] = []
    created_at: datetime


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    stream: bool = False


class QAResponse(BaseModel):
    message_id: int
    role: str = "assistant"
    content: str
    citations: list[dict] = []
