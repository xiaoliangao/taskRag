"""Claim & Conflict Explorer API (Sprint 2, v1.3)."""
from __future__ import annotations

from typing import Sequence

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import OwnedTopicDep, SessionDep
from app.core.errors import NotFoundError
from app.db.models.document import Document
from app.db.models.research_ext import ClaimRelation, PaperClaim
from app.db.repositories.research_ext_repo import (
    ClaimRelationAsyncRepository,
    PaperClaimAsyncRepository,
)
from app.schemas.research_ext import (
    ClaimDocumentRef,
    ConflictDetectResponse,
    ConflictFeedbackBody,
    ConflictRelationPublic,
    PaperClaimPublic,
)

router = APIRouter()


def _claim_to_public(c: PaperClaim) -> PaperClaimPublic:
    return PaperClaimPublic(
        id=c.id,
        document_id=c.document_id,
        claim_text=c.claim_text,
        claim_type=c.claim_type,
        method=c.method,
        dataset=c.dataset,
        metric=c.metric,
        setting=c.setting,
        polarity=c.polarity,
        confidence=c.confidence,
        evidence_text=c.evidence_text,
    )


@router.get(
    "/topics/{topic_id}/claims",
    response_model=list[PaperClaimPublic],
)
async def list_claims(
    topic: OwnedTopicDep,
    db: SessionDep,
    document_id: int | None = Query(None),
    claim_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> list[PaperClaimPublic]:
    items = await PaperClaimAsyncRepository(db).list_for_topic(
        topic.id,
        claim_type=claim_type,
        document_id=document_id,
        limit=limit,
    )
    return [_claim_to_public(c) for c in items]


@router.post(
    "/topics/{topic_id}/claims/extract",
    response_model=ConflictDetectResponse,
)
async def extract_claims(
    topic: OwnedTopicDep,
    limit_docs: int = Query(30, ge=1, le=80),
) -> ConflictDetectResponse:
    try:
        from app.tasks.research_tasks import extract_topic_claims_task

        async_result = extract_topic_claims_task.apply_async(
            kwargs=dict(topic_id=topic.id, limit_docs=limit_docs),
            queue="intelligence",
        )
        return ConflictDetectResponse(
            status="queued", topic_id=topic.id, task_id=str(async_result.id)
        )
    except Exception as exc:
        return ConflictDetectResponse(status=f"failed: {exc}", topic_id=topic.id)


@router.post(
    "/topics/{topic_id}/conflicts/detect",
    response_model=ConflictDetectResponse,
)
async def detect_conflicts(
    topic: OwnedTopicDep,
    extract_first: bool = Query(True),
) -> ConflictDetectResponse:
    try:
        from app.tasks.research_tasks import detect_topic_conflicts_task

        async_result = detect_topic_conflicts_task.apply_async(
            kwargs=dict(topic_id=topic.id, extract_first=extract_first),
            queue="intelligence",
        )
        return ConflictDetectResponse(
            status="queued", topic_id=topic.id, task_id=str(async_result.id)
        )
    except Exception as exc:
        return ConflictDetectResponse(status=f"failed: {exc}", topic_id=topic.id)


@router.get(
    "/topics/{topic_id}/conflicts",
    response_model=list[ConflictRelationPublic],
)
async def list_conflicts(
    topic: OwnedTopicDep,
    db: SessionDep,
    relation_type: str | None = Query(None),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
) -> list[ConflictRelationPublic]:
    rels = await ClaimRelationAsyncRepository(db).list_for_topic(
        topic.id,
        relation_type=relation_type,
        min_confidence=min_confidence,
        limit=limit,
    )
    if not rels:
        return []
    # Bulk fetch claims + docs
    claim_ids = {r.claim_a_id for r in rels} | {r.claim_b_id for r in rels}
    claim_rows = (
        await db.execute(select(PaperClaim).where(PaperClaim.id.in_(claim_ids)))
    ).scalars().all()
    claim_map = {c.id: c for c in claim_rows}
    doc_ids = {c.document_id for c in claim_rows}
    doc_rows = (
        await db.execute(select(Document.id, Document.title).where(Document.id.in_(doc_ids)))
    ).all()
    title_map = {row.id: row.title for row in doc_rows}

    out: list[ConflictRelationPublic] = []
    for r in rels:
        a = claim_map.get(r.claim_a_id)
        b = claim_map.get(r.claim_b_id)
        if not a or not b:
            continue
        out.append(
            ConflictRelationPublic(
                id=r.id,
                topic_id=r.topic_id,
                relation_type=r.relation_type,
                confidence=r.confidence,
                reason_md=r.reason_md,
                evidence=r.evidence_json or {},
                reviewed_by_user=r.reviewed_by_user,
                user_feedback=r.user_feedback,
                claim_a=_claim_to_public(a),
                claim_b=_claim_to_public(b),
                document_a=ClaimDocumentRef(
                    document_id=a.document_id, title=title_map.get(a.document_id)
                ),
                document_b=ClaimDocumentRef(
                    document_id=b.document_id, title=title_map.get(b.document_id)
                ),
            )
        )
    return out


@router.patch("/topics/{topic_id}/conflicts/{relation_id}/feedback")
async def conflict_feedback(
    relation_id: int,
    body: ConflictFeedbackBody,
    topic: OwnedTopicDep,
    db: SessionDep,
) -> dict:
    r = await ClaimRelationAsyncRepository(db).get_by_id(relation_id)
    if not r or r.topic_id != topic.id:
        raise NotFoundError("Conflict relation not found")
    r.reviewed_by_user = True
    r.user_feedback = body.feedback[:64]
    await db.flush()
    await db.commit()
    return {
        "id": r.id,
        "reviewed_by_user": True,
        "user_feedback": r.user_feedback,
    }


__all__ = ["router"]
