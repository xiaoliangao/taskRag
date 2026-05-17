from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, SessionDep
from app.core.errors import NotFoundError
from app.db.repositories.notification_repo import NotificationRepository
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationPublic,
)

router = APIRouter()


def _to_public(n) -> NotificationPublic:
    return NotificationPublic(
        id=n.id,
        type=n.type,
        title=n.title,
        body=n.body,
        payload=n.payload_json or {},
        read_at=n.read_at,
        created_at=n.created_at,
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    db: SessionDep,
    current_user: CurrentUserDep,
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> NotificationListResponse:
    offset = (page - 1) * page_size
    items, total, unread = await NotificationRepository(db).list_for_user(
        current_user.id, unread_only=unread_only, offset=offset, limit=page_size
    )
    return NotificationListResponse(
        items=[_to_public(n) for n in items], total=total, unread_count=unread
    )


@router.patch("/{notification_id}/read", response_model=NotificationPublic)
async def mark_read(notification_id: int, db: SessionDep, current_user: CurrentUserDep) -> NotificationPublic:
    repo = NotificationRepository(db)
    n = await repo.mark_read(current_user.id, notification_id)
    if not n:
        raise NotFoundError("Notification not found")
    await db.commit()
    return _to_public(n)


@router.patch("/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(db: SessionDep, current_user: CurrentUserDep) -> MarkAllReadResponse:
    count = await NotificationRepository(db).mark_all_read(current_user.id)
    await db.commit()
    return MarkAllReadResponse(updated_count=count)
