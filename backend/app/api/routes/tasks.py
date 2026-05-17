from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, OwnedTopicDep, SessionDep
from app.core.constants import CollectionTrigger, TaskStatus
from app.core.errors import APIError, NotFoundError
from app.db.repositories.task_repo import CollectionTaskRepository
from app.db.repositories.topic_repo import TopicRepository
from app.schemas.task import TaskListResponse, TaskProgress, TaskPublic

router = APIRouter()


def _to_public(t) -> TaskPublic:
    raw = (t.metadata_json or {}).get("progress") or {}
    progress = TaskProgress(**raw) if raw else None
    return TaskPublic(
        id=t.id,
        topic_id=t.topic_id,
        source=t.source,
        trigger=t.trigger,
        status=t.status,
        new_docs_count=t.new_docs_count,
        reused_docs_count=t.reused_docs_count,
        skipped_docs_count=t.skipped_docs_count,
        started_at=t.started_at,
        finished_at=t.finished_at,
        error_msg=t.error_msg,
        created_at=t.created_at,
        progress=progress,
    )


@router.get("/topics/{topic_id}/tasks", response_model=TaskListResponse)
async def list_tasks(
    topic: OwnedTopicDep, db: SessionDep, limit: int = Query(50, ge=1, le=200)
) -> TaskListResponse:
    items, total = await CollectionTaskRepository(db).list_for_topic(topic.id, limit=limit)
    return TaskListResponse(items=[_to_public(t) for t in items], total=total)


@router.get("/tasks/{task_id}", response_model=TaskPublic)
async def get_task(task_id: int, db: SessionDep, current_user: CurrentUserDep) -> TaskPublic:
    task = await CollectionTaskRepository(db).get_by_id(task_id)
    if not task:
        raise NotFoundError("Task not found")
    topic = await TopicRepository(db).get_by_id(task.topic_id)
    if not topic or topic.user_id != current_user.id:
        raise NotFoundError("Task not found")
    return _to_public(task)


@router.post("/tasks/{task_id}/retry", response_model=TaskPublic)
async def retry_task(task_id: int, db: SessionDep, current_user: CurrentUserDep) -> TaskPublic:
    repo = CollectionTaskRepository(db)
    task = await repo.get_by_id(task_id)
    if not task:
        raise NotFoundError("Task not found")
    topic = await TopicRepository(db).get_by_id(task.topic_id)
    if not topic or topic.user_id != current_user.id:
        raise NotFoundError("Task not found")
    if task.status != TaskStatus.FAILED.value:
        raise APIError(
            "VALIDATION_ERROR",
            "Only failed tasks can be retried",
            http_status=400,
        )
    # Reset task and enqueue
    task.status = TaskStatus.PENDING.value
    task.error_msg = None
    task.finished_at = None
    task.started_at = None
    await db.commit()
    try:
        from app.tasks.collect_tasks import collect_topic_source_task

        collect_topic_source_task.apply_async(
            kwargs=dict(
                topic_id=task.topic_id,
                source=task.source,
                trigger=CollectionTrigger.MANUAL.value,
                requested_by_user_id=current_user.id,
                collection_task_id=task.id,
            ),
            queue="urgent",
        )
    except Exception:
        pass
    return _to_public(task)
