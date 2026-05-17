from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, SessionDep
from app.db.repositories.user_repo import UserRepository
from app.schemas.settings import SettingsPublic, SettingsUpdate

router = APIRouter()


def _to_public(d: dict) -> SettingsPublic:
    return SettingsPublic(
        timezone=d.get("timezone", "Asia/Singapore"),
        email_notifications_enabled=d.get("email_notifications_enabled", True),
        preferred_llm_provider=d.get("preferred_llm_provider", "deepseek"),
        preferred_llm_model=d.get("preferred_llm_model", "deepseek-chat"),
        preferred_embedding_provider=d.get("preferred_embedding_provider", "siliconflow"),
    )


@router.get("", response_model=SettingsPublic)
async def get_settings(current_user: CurrentUserDep) -> SettingsPublic:
    return _to_public(current_user.settings_json or {})


@router.patch("", response_model=SettingsPublic)
async def update_settings(
    body: SettingsUpdate, db: SessionDep, current_user: CurrentUserDep
) -> SettingsPublic:
    fields = body.model_dump(exclude_unset=True)
    settings = dict(current_user.settings_json or {})
    settings.update(fields)
    await UserRepository(db).update_settings(current_user, settings)
    await db.commit()
    return _to_public(settings)
