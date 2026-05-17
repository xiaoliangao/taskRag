from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.topic import Topic, TopicSourceState


class TopicRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, topic_id: int) -> Topic | None:
        return await self.db.get(Topic, topic_id)

    async def list_for_user(self, user_id: int) -> Sequence[Topic]:
        result = await self.db.execute(
            select(Topic).where(Topic.user_id == user_id).order_by(Topic.created_at.desc())
        )
        return result.scalars().all()

    async def count_for_user(self, user_id: int) -> int:
        result = await self.db.execute(
            select(func.count(Topic.id)).where(Topic.user_id == user_id)
        )
        return result.scalar_one()

    async def get_by_user_and_name(self, user_id: int, name: str) -> Topic | None:
        result = await self.db.execute(
            select(Topic).where(Topic.user_id == user_id, Topic.name == name)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Topic:
        topic = Topic(**kwargs)
        self.db.add(topic)
        await self.db.flush()
        return topic

    async def update(self, topic: Topic, fields: dict) -> Topic:
        for k, v in fields.items():
            setattr(topic, k, v)
        await self.db.flush()
        return topic

    async def delete(self, topic: Topic) -> None:
        await self.db.delete(topic)
        await self.db.flush()


class TopicSourceStateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, topic_id: int, source: str) -> TopicSourceState | None:
        return await self.db.get(TopicSourceState, (topic_id, source))

    async def upsert_initial(self, topic_id: int, source: str) -> None:
        stmt = pg_insert(TopicSourceState).values(topic_id=topic_id, source=source)
        stmt = stmt.on_conflict_do_nothing(index_elements=["topic_id", "source"])
        await self.db.execute(stmt)

    async def mark_success(self, topic_id: int, source: str, fetched_at: datetime) -> None:
        await self.db.execute(
            update(TopicSourceState)
            .where(TopicSourceState.topic_id == topic_id, TopicSourceState.source == source)
            .values(last_fetched_at=fetched_at, last_success_at=fetched_at, last_error_at=None, last_error_msg=None)
        )

    async def mark_failure(self, topic_id: int, source: str, error_msg: str) -> None:
        now = datetime.now(tz=timezone.utc)
        await self.db.execute(
            update(TopicSourceState)
            .where(TopicSourceState.topic_id == topic_id, TopicSourceState.source == source)
            .values(last_fetched_at=now, last_error_at=now, last_error_msg=error_msg[:1000])
        )

    async def list_for_topic(self, topic_id: int) -> Sequence[TopicSourceState]:
        result = await self.db.execute(
            select(TopicSourceState).where(TopicSourceState.topic_id == topic_id)
        )
        return result.scalars().all()

    async def delete_for_source(self, topic_id: int, source: str) -> None:
        await self.db.execute(
            delete(TopicSourceState).where(
                TopicSourceState.topic_id == topic_id, TopicSourceState.source == source
            )
        )
