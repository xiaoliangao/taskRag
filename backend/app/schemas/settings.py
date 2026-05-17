from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SettingsPublic(BaseModel):
    timezone: str = "Asia/Singapore"
    email_notifications_enabled: bool = True
    preferred_llm_provider: str = "deepseek"
    preferred_llm_model: str = "deepseek-chat"
    preferred_embedding_provider: str = "siliconflow"


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timezone: str | None = None
    email_notifications_enabled: bool | None = None
    preferred_llm_provider: str | None = None
    preferred_llm_model: str | None = None
    preferred_embedding_provider: str | None = None
