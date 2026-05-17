"""Hypothesis Verification API (Sprint 3)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUserDep, OwnedTopicDep, SessionDep
from app.core.errors import NotFoundError
from app.db.models.document import Document
from app.db.models.research_ext import HypothesisCheck
from app.schemas.research_ext import (
    HypothesisCheckCreate,
    HypothesisCheckPublic,
    HypothesisCheckSummary,
    HypothesisEvidencePublic,
)
from app.services.hypothesis_service import (
    HypothesisService,
    list_checks,
    list_evidence,
)

router = APIRouter()


async def _to_public(check: HypothesisCheck, db) -> HypothesisCheckPublic:
    evidence_rows = await list_evidence(db, check.id)
    doc_ids = {e.document_id for e in evidence_rows}
    title_map = {}
    if doc_ids:
        rows = (
            await db.execute(select(Document.id, Document.title).where(Document.id.in_(doc_ids)))
        ).all()
        title_map = {r.id: r.title for r in rows}
    return HypothesisCheckPublic(
        id=check.id,
        topic_id=check.topic_id,
        hypothesis=check.hypothesis,
        status=check.status,
        verdict=check.verdict,
        result_md=check.result_md,
        result_json=check.result_json or {},
        confidence=check.confidence,
        error_message=check.error_message,
        created_at=check.created_at,
        finished_at=check.finished_at,
        evidence=[
            HypothesisEvidencePublic(
                id=e.id,
                document_id=e.document_id,
                document_title=title_map.get(e.document_id),
                chunk_id=e.chunk_id,
                stance=e.stance,
                quote=e.quote,
                explanation=e.explanation,
                score=e.score,
            )
            for e in evidence_rows
        ],
    )


@router.post(
    "/topics/{topic_id}/hypotheses/check",
    response_model=HypothesisCheckPublic,
)
async def create_and_run_hypothesis_check(
    body: HypothesisCheckCreate,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> HypothesisCheckPublic:
    if not body.hypothesis.strip():
        raise NotFoundError("hypothesis is required")
    service = HypothesisService(db)
    check = await service.create_check(
        user_id=current_user.id,
        topic_id=topic.id,
        hypothesis=body.hypothesis,
    )
    await db.commit()
    await service.run(check)
    await db.commit()
    return await _to_public(check, db)


@router.get(
    "/topics/{topic_id}/hypotheses",
    response_model=list[HypothesisCheckSummary],
)
async def list_hypotheses(
    topic: OwnedTopicDep,
    db: SessionDep,
    limit: int = Query(20, ge=1, le=100),
) -> list[HypothesisCheckSummary]:
    items = await list_checks(db, topic.id, limit=limit)
    return [
        HypothesisCheckSummary(
            id=h.id,
            topic_id=h.topic_id,
            hypothesis=h.hypothesis,
            status=h.status,
            verdict=h.verdict,
            confidence=h.confidence,
            created_at=h.created_at,
            finished_at=h.finished_at,
        )
        for h in items
    ]


@router.get(
    "/topics/{topic_id}/hypotheses/{check_id}",
    response_model=HypothesisCheckPublic,
)
async def get_hypothesis(
    check_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
) -> HypothesisCheckPublic:
    row = await db.get(HypothesisCheck, check_id)
    if not row or row.topic_id != topic.id:
        raise NotFoundError("Hypothesis check not found")
    return await _to_public(row, db)


@router.delete("/topics/{topic_id}/hypotheses/{check_id}")
async def delete_hypothesis(
    check_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
) -> dict:
    row = await db.get(HypothesisCheck, check_id)
    if not row or row.topic_id != topic.id:
        raise NotFoundError("Hypothesis check not found")
    await db.delete(row)
    await db.commit()
    return {"deleted": True, "id": check_id}


__all__ = ["router"]
