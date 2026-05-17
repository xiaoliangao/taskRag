"""Knowledge Graph API (Sprint 5 MVP)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import OwnedTopicDep, SessionDep
from app.schemas.research_ext import (
    GraphEdge,
    GraphNode,
    GraphRebuildResponse,
    GraphResponse,
)
from app.services.graph_service import list_graph, rebuild_document_relations

router = APIRouter()


@router.get(
    "/topics/{topic_id}/graph",
    response_model=GraphResponse,
)
async def get_graph(
    topic: OwnedTopicDep,
    db: SessionDep,
    relation_types: str | None = Query(None),
    limit_nodes: int = Query(80, ge=10, le=200),
) -> GraphResponse:
    rt = [s.strip() for s in (relation_types or "").split(",") if s.strip()] or None
    data = await list_graph(db, topic.id, relation_types=rt, limit_nodes=limit_nodes)
    return GraphResponse(
        nodes=[GraphNode(**n) for n in data["nodes"]],
        edges=[GraphEdge(**e) for e in data["edges"]],
    )


@router.post(
    "/topics/{topic_id}/graph/rebuild",
    response_model=GraphRebuildResponse,
)
async def rebuild_graph(
    topic: OwnedTopicDep,
    db: SessionDep,
) -> GraphRebuildResponse:
    stats = await rebuild_document_relations(db, topic.id)
    await db.commit()
    return GraphRebuildResponse(status="success", **stats)


__all__ = ["router"]
