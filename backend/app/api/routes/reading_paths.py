"""Reading Path API."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUserDep, OwnedTopicDep, SessionDep
from app.db.models.document import Document
from app.db.repositories.intel_repo import (
    ReadingPathAsyncRepository,
    UserDocStateAsyncRepository,
)

router = APIRouter()


class ReadingPathItemPublic(BaseModel):
    id: int
    document_id: int
    document_title: str
    order_index: int
    stage: str | None
    reason: str | None
    expected_minutes: int | None
    prerequisite_document_ids: list[int] = []
    user_status: str | None = None


class ReadingPathPublic(BaseModel):
    id: int
    topic_id: int
    title: str
    description: str | None
    status: str
    generated_at: str | None
    items: list[ReadingPathItemPublic]


@router.get("/topics/{topic_id}/reading-paths/latest", response_model=ReadingPathPublic | None)
async def get_latest_path(
    topic: OwnedTopicDep, db: SessionDep, current_user: CurrentUserDep
) -> ReadingPathPublic | None:
    repo = ReadingPathAsyncRepository(db)
    p = await repo.get_latest(topic.id)
    if not p:
        return None
    items = await repo.items_for_path(p.id)
    doc_ids = [it.document_id for it in items]
    # Fetch titles
    if doc_ids:
        r = await db.execute(select(Document.id, Document.title).where(Document.id.in_(doc_ids)))
        title_by_id = {row[0]: row[1] for row in r.all()}
    else:
        title_by_id = {}
    states = await UserDocStateAsyncRepository(db).get_many(current_user.id, doc_ids)
    return ReadingPathPublic(
        id=p.id,
        topic_id=p.topic_id,
        title=p.title,
        description=p.description,
        status=p.status,
        generated_at=p.generated_at.isoformat() if p.generated_at else None,
        items=[
            ReadingPathItemPublic(
                id=it.id,
                document_id=it.document_id,
                document_title=title_by_id.get(it.document_id, "(unknown)"),
                order_index=it.order_index,
                stage=it.stage,
                reason=it.reason,
                expected_minutes=it.expected_minutes,
                prerequisite_document_ids=list(it.prerequisite_document_ids or []),
                user_status=states[it.document_id].status if it.document_id in states else None,
            )
            for it in items
        ],
    )


@router.post("/topics/{topic_id}/reading-paths/generate")
async def generate_path(topic: OwnedTopicDep) -> dict:
    try:
        from app.tasks.intel_tasks import generate_reading_path_task

        generate_reading_path_task.apply_async(
            kwargs=dict(topic_id=topic.id), queue="intelligence"
        )
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}
    return {"status": "queued", "topic_id": topic.id}
