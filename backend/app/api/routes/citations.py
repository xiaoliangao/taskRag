"""Citation-graph API — real "A cites B" network for a topic, from OpenAlex."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import OwnedTopicDep, SessionDep
from app.services.citation_graph_service import (
    enrich_topic_citations,
    get_citation_graph,
    rebuild_citation_edges,
)

router = APIRouter()


class CitationNode(BaseModel):
    id: int
    title: str | None
    year: int | None
    source: str | None
    cited_by_count: int | None
    recent_citations: int
    in_degree: int
    out_degree: int


class CitationEdge(BaseModel):
    source: int  # citing document id
    target: int  # cited document id


class CitationGraphResponse(BaseModel):
    nodes: list[CitationNode]
    edges: list[CitationEdge]
    stats: dict[str, Any]


class CitationRebuildResponse(BaseModel):
    status: str
    enriched: int
    remaining: int
    edges: int
    nodes: int


@router.get("/topics/{topic_id}/citation-graph", response_model=CitationGraphResponse)
async def get_citation_graph_route(
    topic: OwnedTopicDep, db: SessionDep
) -> CitationGraphResponse:
    data = await get_citation_graph(db, topic.id)
    return CitationGraphResponse(
        nodes=[CitationNode(**n) for n in data["nodes"]],
        edges=[CitationEdge(**e) for e in data["edges"]],
        stats=data["stats"],
    )


@router.post("/topics/{topic_id}/citation-graph/rebuild", response_model=CitationRebuildResponse)
async def rebuild_citation_graph_route(
    topic: OwnedTopicDep, db: SessionDep
) -> CitationRebuildResponse:
    """Fetch citation metadata from OpenAlex (capped, idempotent) then rebuild
    the directed citation edges. Synchronous — a manual admin-ish action with a
    loading state on the client; remaining>0 means click again to continue."""
    enr = await enrich_topic_citations(db, topic.id)
    edge_stats = await rebuild_citation_edges(db, topic.id)
    await db.commit()
    return CitationRebuildResponse(
        status="success",
        enriched=enr["enriched"],
        remaining=enr["remaining"],
        edges=edge_stats["edges"],
        nodes=edge_stats["nodes"],
    )


__all__ = ["router"]
