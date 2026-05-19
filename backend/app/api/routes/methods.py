"""Method Timeline API (v1.5 A-3)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import OwnedTopicDep, SessionDep
from app.db.models.research_ext import MethodEntity, MethodEvolutionEdge

router = APIRouter()


class MethodEntityPublic(BaseModel):
    id: int
    name: str
    normalized_name: str
    description: str | None
    first_seen_document_id: int | None
    first_seen_at: datetime | None
    document_count: int


class MethodEdgePublic(BaseModel):
    id: int
    from_method_id: int
    to_method_id: int
    relation_type: str
    confidence: float
    explanation: str | None


class MethodTimelineResponse(BaseModel):
    methods: list[MethodEntityPublic]
    edges: list[MethodEdgePublic]


class RebuildResponse(BaseModel):
    status: str
    task_id: str | None = None


@router.get(
    "/topics/{topic_id}/methods/timeline",
    response_model=MethodTimelineResponse,
)
async def get_method_timeline(
    topic: OwnedTopicDep,
    db: SessionDep,
) -> MethodTimelineResponse:
    from sqlalchemy import select

    methods = (
        await db.execute(
            select(MethodEntity)
            .where(MethodEntity.topic_id == topic.id)
            .order_by(
                MethodEntity.first_seen_at.asc().nullslast(),
                MethodEntity.document_count.desc(),
            )
        )
    ).scalars().all()
    edges = (
        await db.execute(
            select(MethodEvolutionEdge)
            .where(MethodEvolutionEdge.topic_id == topic.id)
            .order_by(MethodEvolutionEdge.confidence.desc())
        )
    ).scalars().all()

    return MethodTimelineResponse(
        methods=[
            MethodEntityPublic(
                id=m.id,
                name=m.name,
                normalized_name=m.normalized_name,
                description=m.description,
                first_seen_document_id=m.first_seen_document_id,
                first_seen_at=m.first_seen_at,
                document_count=m.document_count,
            )
            for m in methods
        ],
        edges=[
            MethodEdgePublic(
                id=e.id,
                from_method_id=e.from_method_id,
                to_method_id=e.to_method_id,
                relation_type=e.relation_type,
                confidence=e.confidence,
                explanation=e.explanation,
            )
            for e in edges
        ],
    )


@router.post(
    "/topics/{topic_id}/methods/timeline/rebuild",
    response_model=RebuildResponse,
)
async def rebuild_method_timeline(
    topic: OwnedTopicDep,
    extract_edges: bool = True,
) -> RebuildResponse:
    try:
        from app.tasks.research_tasks import rebuild_method_timeline_task

        res = rebuild_method_timeline_task.apply_async(
            kwargs={"topic_id": topic.id, "extract_edges": extract_edges},
            queue="intelligence",
        )
        return RebuildResponse(status="queued", task_id=str(res.id))
    except Exception as exc:
        return RebuildResponse(status=f"failed: {exc}")


__all__ = ["router"]
