from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUserDep, OwnedTopicDep, SessionDep
from app.core.config import get_settings
from app.schemas.picker import (
    CollectSelectedRequest,
    CollectSelectedResponse,
    PreviewRequest,
    PreviewResponse,
)
from app.schemas.topic import CollectTriggerResponse, TopicCreate, TopicPublic, TopicUpdate
from app.services.picker_service import search_preview
from app.services.topic_service import TopicService

router = APIRouter()


@router.get("", response_model=list[TopicPublic])
async def list_topics(db: SessionDep, current_user: CurrentUserDep) -> list[TopicPublic]:
    return await TopicService(db).list_for_user(current_user)


@router.post("", response_model=TopicPublic, status_code=status.HTTP_201_CREATED)
async def create_topic(
    body: TopicCreate, db: SessionDep, current_user: CurrentUserDep
) -> TopicPublic:
    svc = TopicService(db)
    topic = await svc.create(current_user, body)
    return await svc.to_public(topic)


@router.get("/{topic_id}", response_model=TopicPublic)
async def get_topic(topic: OwnedTopicDep, db: SessionDep) -> TopicPublic:
    return await TopicService(db).to_public(topic)


@router.patch("/{topic_id}", response_model=TopicPublic)
async def update_topic(
    body: TopicUpdate, topic: OwnedTopicDep, db: SessionDep
) -> TopicPublic:
    svc = TopicService(db)
    updated = await svc.update(topic, body)
    return await svc.to_public(updated)


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(topic: OwnedTopicDep, db: SessionDep) -> Response:
    await TopicService(db).delete(topic)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{topic_id}/collect", response_model=CollectTriggerResponse)
async def collect_topic(
    topic: OwnedTopicDep, db: SessionDep, current_user: CurrentUserDep
) -> CollectTriggerResponse:
    """Legacy: direct fire-and-forget collect. UI now uses search-preview + collect-selected."""
    tasks = await TopicService(db).manual_collect(topic, current_user.id)
    return CollectTriggerResponse(tasks=tasks)


@router.post("/{topic_id}/search-preview", response_model=PreviewResponse)
async def topic_search_preview(
    body: PreviewRequest, topic: OwnedTopicDep, db: SessionDep
) -> PreviewResponse:
    settings = get_settings()
    limit = body.limit or settings.manual_preview_max_results
    return await search_preview(
        db=db,
        topic_id=topic.id,
        topic_keywords=topic.keywords or [],
        topic_sources=list(topic.sources or []),
        chosen_sources=body.sources,
        limit=limit,
    )


@router.post("/{topic_id}/collect-selected", response_model=CollectSelectedResponse)
async def topic_collect_selected(
    body: CollectSelectedRequest,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> CollectSelectedResponse:
    from app.core.constants import CollectionTrigger
    from app.db.repositories.task_repo import CollectionTaskRepository

    repo = CollectionTaskRepository(db)
    task = await repo.create(
        topic_id=topic.id,
        source="manual_pick",
        trigger=CollectionTrigger.MANUAL.value,
        requested_by_user_id=current_user.id,
    )
    await db.commit()

    try:
        from app.tasks.collect_tasks import ingest_picked_documents_task

        # serialize picks for celery (they're PreviewItem; use dict)
        picks_payload = [p.model_dump(mode="json") for p in body.picks]
        ingest_picked_documents_task.apply_async(
            kwargs=dict(
                topic_id=topic.id,
                picks=picks_payload,
                collection_task_id=task.id,
                requested_by_user_id=current_user.id,
            ),
            queue="urgent",
        )
    except Exception:
        pass
    return CollectSelectedResponse(task_id=task.id, count=len(body.picks), status="queued")
