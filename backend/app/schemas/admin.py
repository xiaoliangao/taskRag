from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminUserRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime
    is_admin: bool
    disabled_at: datetime | None
    topic_count: int = 0
    document_count: int = 0


class AdminUserList(BaseModel):
    items: list[AdminUserRow]
    total: int
    page: int
    page_size: int


class AdminUserPatch(BaseModel):
    is_admin: bool | None = None
    disabled: bool | None = None  # None=no change, True=disable, False=enable


class AdminResetPasswordResponse(BaseModel):
    delivery: str  # "email" | "log"
    new_password_preview: str | None = None  # populated when delivery == "log"


class AdminBroadcastRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)
    target: str = Field(default="all", pattern=r"^(all|selected)$")
    user_ids: list[int] = Field(default_factory=list)


class AdminBroadcastResponse(BaseModel):
    queued: int
    skipped: int
    delivery: str  # "email" | "log"


class AdminHealthComponent(BaseModel):
    name: str
    status: str  # "ok" | "warn" | "fail" | "skipped"
    detail: str | None = None
    latency_ms: float | None = None


class AdminHealthReport(BaseModel):
    checked_at: datetime
    components: list[AdminHealthComponent]


class AdminUserCreate(BaseModel):
    """Reserved for future use — admin-created accounts skip verification code."""
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)
    is_admin: bool = False
