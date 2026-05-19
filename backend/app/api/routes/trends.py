"""Trend Radar API (Sprint 1, v1.3)."""
from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OwnedTopicDep, SessionDep
from app.core.errors import NotFoundError
from app.db.models.document import Document, TopicDocument
from app.db.models.research_ext import TopicTrendItem, TopicTrendRun
from app.db.repositories.research_ext_repo import (
    TopicTermAsyncRepository,
    TopicTrendAsyncRepository,
)
from app.schemas.research_ext import (
    TermDocumentRef,
    TopicTermPublic,
    TrendGenerateResponse,
    TrendItemPublic,
    TrendRunPublic,
    TrendRunSummary,
)

router = APIRouter()


def _items_to_public(items: Sequence[TopicTrendItem]) -> list[TrendItemPublic]:
    out: list[TrendItemPublic] = []
    for it in items:
        out.append(
            TrendItemPublic(
                id=it.id,
                term=it.term,
                term_type=it.term_type,
                status=it.status,
                frequency_recent=it.frequency_recent,
                frequency_baseline=it.frequency_baseline,
                growth_rate=it.growth_rate,
                confidence=it.confidence,
                evidence_document_ids=list(it.evidence_document_ids or []),
                explanation=it.explanation,
            )
        )
    return out


async def _run_to_public(run: TopicTrendRun, db: AsyncSession) -> TrendRunPublic:
    items = await TopicTrendAsyncRepository(db).list_items(run.id)
    return TrendRunPublic(
        id=run.id,
        topic_id=run.topic_id,
        window_days=run.window_days,
        bucket=run.bucket,
        status=run.status,
        summary_md=run.summary_md,
        heatmap=run.heatmap_json or {},
        items=_items_to_public(items),
        error_message=run.error_message,
        generated_at=run.generated_at,
        created_at=run.created_at,
    )


@router.get(
    "/topics/{topic_id}/trends/latest",
    response_model=TrendRunPublic | None,
)
async def get_latest_trend(
    topic: OwnedTopicDep,
    db: SessionDep,
    window_days: int = Query(60, ge=7, le=365),
) -> TrendRunPublic | None:
    repo = TopicTrendAsyncRepository(db)
    run = await repo.get_latest_run(topic.id, window_days=window_days)
    if run is None:
        run = await repo.get_latest_run(topic.id, window_days=None)
    if run is None:
        return None
    return await _run_to_public(run, db)


@router.get(
    "/topics/{topic_id}/trends/runs",
    response_model=list[TrendRunSummary],
)
async def list_trend_runs(
    topic: OwnedTopicDep,
    db: SessionDep,
) -> list[TrendRunSummary]:
    runs = await TopicTrendAsyncRepository(db).list_runs(topic.id)
    return [
        TrendRunSummary(
            id=r.id,
            topic_id=r.topic_id,
            window_days=r.window_days,
            bucket=r.bucket,
            status=r.status,
            generated_at=r.generated_at,
            created_at=r.created_at,
        )
        for r in runs
    ]


@router.get(
    "/topics/{topic_id}/trends/runs/{run_id}",
    response_model=TrendRunPublic,
)
async def get_trend_run(
    run_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
) -> TrendRunPublic:
    run = await TopicTrendAsyncRepository(db).get_run(run_id)
    if not run or run.topic_id != topic.id:
        raise NotFoundError("Trend run not found")
    return await _run_to_public(run, db)


@router.post(
    "/topics/{topic_id}/trends/generate",
    response_model=TrendGenerateResponse,
)
async def generate_trend(
    topic: OwnedTopicDep,
    window_days: int = Query(60, ge=7, le=365),
) -> TrendGenerateResponse:
    try:
        from app.tasks.research_tasks import generate_topic_trend_task

        async_result = generate_topic_trend_task.apply_async(
            kwargs=dict(topic_id=topic.id, window_days=window_days),
            queue="intelligence",
        )
        return TrendGenerateResponse(
            status="queued", topic_id=topic.id, task_id=str(async_result.id)
        )
    except Exception as exc:
        return TrendGenerateResponse(status=f"failed: {exc}", topic_id=topic.id)


@router.get(
    "/topics/{topic_id}/terms",
    response_model=list[TopicTermPublic],
)
async def list_terms(
    topic: OwnedTopicDep,
    db: SessionDep,
    term_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[TopicTermPublic]:
    terms = await TopicTermAsyncRepository(db).list_for_topic(
        topic.id, term_type=term_type, limit=limit
    )
    return [
        TopicTermPublic(
            id=t.id,
            term=t.term,
            normalized_term=t.normalized_term,
            term_type=t.term_type,
            document_count=t.document_count,
            occurrence_count=t.occurrence_count,
            first_seen_at=t.first_seen_at,
            last_seen_at=t.last_seen_at,
        )
        for t in terms
    ]


@router.get(
    "/topics/{topic_id}/terms/{term_id}/documents",
    response_model=list[TermDocumentRef],
)
async def list_documents_for_term(
    term_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
) -> list[TermDocumentRef]:
    term = await TopicTermAsyncRepository(db).get_by_id(term_id)
    if not term or term.topic_id != topic.id:
        raise NotFoundError("Term not found")
    doc_ids = await TopicTermAsyncRepository(db).list_documents_for_term(term_id)
    if not doc_ids:
        return []
    # filter docs that belong to this topic and fetch metadata
    rows = await db.execute(
        select(Document)
        .join(TopicDocument, TopicDocument.document_id == Document.id)
        .where(
            TopicDocument.topic_id == topic.id,
            Document.id.in_(doc_ids),
        )
        .order_by(Document.published_at.desc().nullslast())
    )
    docs = rows.scalars().all()
    return [
        TermDocumentRef(
            document_id=d.id,
            title=d.title,
            published_at=d.published_at,
            source=d.source,
        )
        for d in docs
    ]


__all__ = ["router"]
