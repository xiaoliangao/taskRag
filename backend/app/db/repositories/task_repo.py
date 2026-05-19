from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TaskStatus
from app.db.models.task import CollectionTask


class CollectionTaskRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, task_id: int) -> CollectionTask | None:
        return await self.db.get(CollectionTask, task_id)

    async def create(
        self,
        *,
        topic_id: int,
        source: str,
        trigger: str,
        requested_by_user_id: int | None = None,
        status: str = TaskStatus.PENDING.value,
    ) -> CollectionTask:
        task = CollectionTask(
            topic_id=topic_id,
            source=source,
            trigger=trigger,
            status=status,
            requested_by_user_id=requested_by_user_id,
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def mark_running(self, task: CollectionTask) -> None:
        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.now(tz=UTC)
        await self.db.flush()

    async def mark_success(
        self,
        task: CollectionTask,
        *,
        new_docs: int,
        reused_docs: int,
        skipped_docs: int,
    ) -> None:
        task.status = TaskStatus.SUCCESS.value
        task.finished_at = datetime.now(tz=UTC)
        task.new_docs_count = new_docs
        task.reused_docs_count = reused_docs
        task.skipped_docs_count = skipped_docs
        await self.db.flush()

    async def mark_failed(self, task: CollectionTask, error_msg: str) -> None:
        task.status = TaskStatus.FAILED.value
        task.finished_at = datetime.now(tz=UTC)
        task.error_msg = error_msg[:2000]
        await self.db.flush()

    async def list_for_topic(self, topic_id: int, *, limit: int = 50) -> tuple[Sequence[CollectionTask], int]:
        base = select(CollectionTask).where(CollectionTask.topic_id == topic_id).order_by(
            CollectionTask.created_at.desc()
        )
        items = (await self.db.execute(base.limit(limit))).scalars().all()
        total = int((await self.db.execute(
            select(func.count(CollectionTask.id)).where(CollectionTask.topic_id == topic_id)
        )).scalar_one() or 0)
        return items, total

    async def latest_for_topic(self, topic_id: int) -> CollectionTask | None:
        result = await self.db.execute(
            select(CollectionTask)
            .where(CollectionTask.topic_id == topic_id, CollectionTask.status == TaskStatus.SUCCESS.value)
            .order_by(CollectionTask.finished_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
