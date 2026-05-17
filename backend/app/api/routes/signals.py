"""Breakthrough / signal API (Sprint 2, v1.3)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import OwnedTopicDep, SessionDep
from app.db.models.document import Document
from app.db.repositories.research_ext_repo import DocumentSignalAsyncRepository
from app.schemas.research_ext import DocumentSignalPublic, SignalRefreshResponse

router = APIRouter()


@router.get(
    "/topics/{topic_id}/signals",
    response_model=list[DocumentSignalPublic],
)
async def list_signals(
    topic: OwnedTopicDep,
    db: SessionDep,
    signal_type: str | None = Query(None),
    limit: int = Query(30, ge=1, le=200),
) -> list[DocumentSignalPublic]:
    rows = await DocumentSignalAsyncRepository(db).list_for_topic(
        topic.id, signal_type=signal_type, limit=limit
    )
    if not rows:
        return []
    doc_ids = {r.document_id for r in rows}
    docs = (
        await db.execute(select(Document.id, Document.title).where(Document.id.in_(doc_ids)))
    ).all()
    title_map = {row.id: row.title for row in docs}
    return [
        DocumentSignalPublic(
            id=r.id,
            document_id=r.document_id,
            document_title=title_map.get(r.document_id),
            signal_type=r.signal_type,
            score=r.score,
            reason_md=r.reason_md,
            evidence=r.evidence_json or {},
            source=r.source,
            detected_at=r.detected_at,
        )
        for r in rows
    ]


@router.post(
    "/topics/{topic_id}/signals/refresh",
    response_model=SignalRefreshResponse,
)
async def refresh_signals(topic: OwnedTopicDep) -> SignalRefreshResponse:
    try:
        from app.tasks.research_tasks import refresh_topic_signals_task

        async_result = refresh_topic_signals_task.apply_async(
            kwargs=dict(topic_id=topic.id),
            queue="intelligence",
        )
        return SignalRefreshResponse(
            status="queued", topic_id=topic.id, task_id=str(async_result.id)
        )
    except Exception as exc:
        return SignalRefreshResponse(status=f"failed: {exc}", topic_id=topic.id)


__all__ = ["router"]
