"""Export Hub API (Sprint 5 MVP)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import OwnedTopicDep, SessionDep
from app.schemas.research_ext import ExportPayload
from app.services.export_service import export_bibtex, export_markdown_bundle

router = APIRouter()


@router.post(
    "/topics/{topic_id}/exports/bibtex",
    response_model=ExportPayload,
)
async def export_topic_bibtex(
    topic: OwnedTopicDep,
    db: SessionDep,
) -> ExportPayload:
    content = await export_bibtex(db, topic.id)
    return ExportPayload(export_type="bibtex", content=content, char_count=len(content))


@router.post(
    "/topics/{topic_id}/exports/markdown",
    response_model=ExportPayload,
)
async def export_topic_markdown(
    topic: OwnedTopicDep,
    db: SessionDep,
) -> ExportPayload:
    content = await export_markdown_bundle(db, topic.id)
    return ExportPayload(
        export_type="markdown", content=content, char_count=len(content)
    )


@router.post(
    "/topics/{topic_id}/exports",
    response_model=ExportPayload,
)
async def export_dispatch(
    topic: OwnedTopicDep,
    db: SessionDep,
    export_type: str = Query("bibtex"),
) -> ExportPayload:
    if export_type == "bibtex":
        return await export_topic_bibtex(topic=topic, db=db)
    if export_type == "markdown":
        return await export_topic_markdown(topic=topic, db=db)
    raise HTTPException(status_code=400, detail="unsupported export_type")


__all__ = ["router"]
