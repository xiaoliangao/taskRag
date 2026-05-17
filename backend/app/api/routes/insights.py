"""Research Insights API (Gap, Opportunity, Risk, Trend)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import OwnedTopicDep, SessionDep
from app.core.errors import NotFoundError
from app.db.repositories.intel_repo import InsightAsyncRepository

router = APIRouter()


class InsightPublic(BaseModel):
    id: int
    topic_id: int
    insight_type: str
    status: str
    title: str
    summary: str | None
    detail_md: str | None
    confidence: float | None
    evidence_document_ids: list[int]
    evidence_chunk_ids: list[int]
    suggested_questions: list[str]
    suggested_experiments: list[str]
    generated_at: str | None


def _to_public(i) -> InsightPublic:
    return InsightPublic(
        id=i.id,
        topic_id=i.topic_id,
        insight_type=i.insight_type,
        status=i.status,
        title=i.title,
        summary=i.summary,
        detail_md=i.detail_md,
        confidence=i.confidence,
        evidence_document_ids=list(i.evidence_document_ids or []),
        evidence_chunk_ids=list(i.evidence_chunk_ids or []),
        suggested_questions=list(i.suggested_questions or []),
        suggested_experiments=list(i.suggested_experiments or []),
        generated_at=i.generated_at.isoformat() if i.generated_at else None,
    )


@router.get("/topics/{topic_id}/insights", response_model=list[InsightPublic])
async def list_insights(
    topic: OwnedTopicDep,
    db: SessionDep,
    type: str | None = Query(default=None, description="filter by insight_type, e.g. 'gap'"),
) -> list[InsightPublic]:
    items = await InsightAsyncRepository(db).list_for_topic(topic.id, insight_type=type)
    return [_to_public(i) for i in items]


@router.get("/topics/{topic_id}/insights/{insight_id}", response_model=InsightPublic)
async def get_insight(insight_id: int, topic: OwnedTopicDep, db: SessionDep) -> InsightPublic:
    i = await InsightAsyncRepository(db).get_by_id(insight_id)
    if not i or i.topic_id != topic.id:
        raise NotFoundError("Insight not found")
    return _to_public(i)


@router.post("/topics/{topic_id}/insights/gaps/generate")
async def generate_gaps(topic: OwnedTopicDep) -> dict:
    try:
        from app.tasks.intel_tasks import generate_research_gaps_task

        generate_research_gaps_task.apply_async(
            kwargs=dict(topic_id=topic.id), queue="intelligence"
        )
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}
    return {"status": "queued", "topic_id": topic.id}
