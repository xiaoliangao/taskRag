from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.notification import Notification, NotificationDelivery


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        type: str,
        title: str,
        body: str,
        payload: dict | None = None,
    ) -> Notification:
        n = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            payload_json=payload or {},
        )
        self.db.add(n)
        await self.db.flush()
        return n

    async def list_for_user(
        self,
        user_id: int,
        *,
        unread_only: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Notification], int, int]:
        conds = [Notification.user_id == user_id]
        if unread_only:
            conds.append(Notification.read_at.is_(None))
        base = select(Notification).where(*conds).order_by(Notification.created_at.desc())
        items = (await self.db.execute(base.offset(offset).limit(limit))).scalars().all()
        total = int((await self.db.execute(
            select(func.count(Notification.id)).where(*conds)
        )).scalar_one() or 0)
        unread = int((await self.db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.read_at.is_(None)
            )
        )).scalar_one() or 0)
        return items, total, unread

    async def mark_read(self, user_id: int, notification_id: int) -> Notification | None:
        n = await self.db.get(Notification, notification_id)
        if not n or n.user_id != user_id:
            return None
        if n.read_at is None:
            n.read_at = datetime.now(tz=UTC)
            await self.db.flush()
        return n

    async def mark_all_read(self, user_id: int) -> int:
        now = datetime.now(tz=UTC)
        result = await self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=now)
        )
        return result.rowcount or 0


class NotificationDeliveryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(self, *, notification_id: int, channel: str, status: str, error_msg: str | None = None) -> None:
        self.db.add(NotificationDelivery(
            notification_id=notification_id,
            channel=channel,
            status=status,
            error_msg=error_msg,
        ))
        await self.db.flush()
