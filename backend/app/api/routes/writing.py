"""Related Work Studio API (Sprint 4)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUserDep, OwnedTopicDep, SessionDep
from app.core.errors import NotFoundError
from app.db.models.research_ext import WritingProjectSource
from app.schemas.research_ext import (
    WritingProjectCreate,
    WritingProjectPublic,
    WritingProjectSummary,
)
from app.services.writing_service import (
    WritingService,
    get_project,
    list_projects,
)

router = APIRouter()


async def _to_public(project, db) -> WritingProjectPublic:
    src_rows = (
        await db.execute(
            select(WritingProjectSource.document_id).where(
                WritingProjectSource.writing_project_id == project.id
            )
        )
    ).all()
    return WritingProjectPublic(
        id=project.id,
        topic_id=project.topic_id,
        title=project.title,
        writing_type=project.writing_type,
        user_intent=project.user_intent,
        status=project.status,
        scope_json=project.scope_json or {},
        outline_json=project.outline_json or {},
        draft_md=project.draft_md,
        citation_json=project.citation_json or [],
        error_message=project.error_message,
        created_at=project.created_at,
        updated_at=project.updated_at,
        document_ids=[r[0] for r in src_rows],
    )


@router.post(
    "/topics/{topic_id}/writing-projects",
    response_model=WritingProjectPublic,
)
async def create_writing_project(
    body: WritingProjectCreate,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> WritingProjectPublic:
    try:
        project = await WritingService(db).create_project(
            user_id=current_user.id,
            topic_id=topic.id,
            title=body.title,
            user_intent=body.user_intent,
            document_ids=body.document_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return await _to_public(project, db)


@router.get(
    "/topics/{topic_id}/writing-projects",
    response_model=list[WritingProjectSummary],
)
async def list_writing_projects(
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
    limit: int = Query(30, ge=1, le=100),
) -> list[WritingProjectSummary]:
    items = await list_projects(db, current_user.id, topic.id, limit=limit)
    return [
        WritingProjectSummary(
            id=p.id,
            topic_id=p.topic_id,
            title=p.title,
            writing_type=p.writing_type,
            status=p.status,
            error_message=p.error_message,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in items
    ]


@router.get(
    "/topics/{topic_id}/writing-projects/{project_id}",
    response_model=WritingProjectPublic,
)
async def get_writing_project(
    project_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> WritingProjectPublic:
    p = await get_project(db, project_id)
    if not p or p.topic_id != topic.id or p.user_id != current_user.id:
        raise NotFoundError("Writing project not found")
    return await _to_public(p, db)


@router.post(
    "/topics/{topic_id}/writing-projects/{project_id}/generate-outline",
    response_model=WritingProjectPublic,
)
async def generate_outline(
    project_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> WritingProjectPublic:
    """Queue outline generation. Returns immediately; client polls."""
    p = await get_project(db, project_id)
    if not p or p.topic_id != topic.id or p.user_id != current_user.id:
        raise NotFoundError("Writing project not found")
    p.status = "outline_pending"
    p.error_message = None
    await db.flush()
    await db.commit()
    try:
        from app.tasks.research_tasks import generate_writing_outline_task

        generate_writing_outline_task.apply_async(
            kwargs={"project_id": project_id},
            queue="intelligence",
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("outline_dispatch_failed: %s", exc)
    return await _to_public(p, db)


@router.post(
    "/topics/{topic_id}/writing-projects/{project_id}/generate-draft",
    response_model=WritingProjectPublic,
)
async def generate_draft(
    project_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> WritingProjectPublic:
    """Queue draft generation. Returns immediately; client polls."""
    p = await get_project(db, project_id)
    if not p or p.topic_id != topic.id or p.user_id != current_user.id:
        raise NotFoundError("Writing project not found")
    p.status = "draft_pending"
    p.error_message = None
    await db.flush()
    await db.commit()
    try:
        from app.tasks.research_tasks import generate_writing_draft_task

        generate_writing_draft_task.apply_async(
            kwargs={"project_id": project_id},
            queue="intelligence",
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("draft_dispatch_failed: %s", exc)
    return await _to_public(p, db)


@router.get(
    "/topics/{topic_id}/writing-projects/{project_id}/export",
)
async def export_writing(
    project_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
    fmt: str = Query("markdown", alias="format"),
) -> dict:
    p = await get_project(db, project_id)
    if not p or p.topic_id != topic.id or p.user_id != current_user.id:
        raise NotFoundError("Writing project not found")
    if fmt != "markdown":
        raise HTTPException(status_code=400, detail="only markdown format supported in v1.3")
    return {
        "format": "markdown",
        "content": p.draft_md or "",
        "citations": p.citation_json or [],
    }


__all__ = ["router"]
