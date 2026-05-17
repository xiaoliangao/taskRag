"""Briefing + topic insight + per-user doc state API."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, OwnedTopicDep, SessionDep
from app.core.errors import NotFoundError
from app.db.repositories.document_repo import DocumentRepository, TopicDocumentRepository
from app.db.repositories.intel_repo import (
    BriefingAsyncRepository,
    TopicInsightAsyncRepository,
    UserDocStateAsyncRepository,
)
from app.schemas.briefing import (
    BriefingGenerateResponse,
    BriefingPublic,
    DocumentBriefingResponse,
    TopicInsightPublic,
    UserDocStatePublic,
    UserDocStateUpdate,
)

router = APIRouter()


async def _ensure_doc_in_topic(db, topic_id: int, document_id: int):
    assoc = await TopicDocumentRepository(db).get_association(topic_id, document_id)
    if not assoc:
        raise NotFoundError("Document not found in this topic")


def _briefing_to_public(b) -> BriefingPublic:
    return BriefingPublic(
        status=b.status,
        language=b.language,
        one_sentence_summary=b.one_sentence_summary,
        problem=b.problem,
        method=b.method,
        contributions=b.contributions or [],
        experiments=b.experiments or [],
        limitations=b.limitations or [],
        datasets=b.datasets or [],
        metrics=b.metrics or [],
        code_available=b.code_available,
        code_url=b.code_url,
        reading_time_minutes=b.reading_time_minutes,
        evidence_chunk_ids=b.evidence_chunk_ids or [],
        generated_at=b.generated_at,
    )


def _insight_to_public(i) -> TopicInsightPublic:
    return TopicInsightPublic(
        relevance_score=i.relevance_score,
        relevance_reason=i.relevance_reason,
        reading_priority=i.reading_priority,
        why_read=i.why_read,
        tags=i.tags or [],
    )


def _state_to_public(s) -> UserDocStatePublic:
    return UserDocStatePublic(
        status=s.status,
        favorite=s.favorite,
        rating=s.rating,
        personal_note=s.personal_note,
        tags=s.tags or [],
        last_opened_at=s.last_opened_at,
    )


@router.get(
    "/topics/{topic_id}/documents/{document_id}/briefing",
    response_model=DocumentBriefingResponse,
)
async def get_briefing(
    document_id: int, topic: OwnedTopicDep, db: SessionDep, current_user: CurrentUserDep
) -> DocumentBriefingResponse:
    await _ensure_doc_in_topic(db, topic.id, document_id)
    doc = await DocumentRepository(db).get_by_id(document_id)
    if not doc:
        raise NotFoundError("Document not found")

    b = await BriefingAsyncRepository(db).get(document_id)
    i = await TopicInsightAsyncRepository(db).get(topic.id, document_id)
    s = await UserDocStateAsyncRepository(db).get(current_user.id, document_id)

    return DocumentBriefingResponse(
        document_id=document_id,
        title=doc.title,
        briefing=_briefing_to_public(b) if b else None,
        topic_insight=_insight_to_public(i) if i else None,
        user_state=_state_to_public(s) if s else None,
    )


@router.post(
    "/topics/{topic_id}/documents/{document_id}/briefing/generate",
    response_model=BriefingGenerateResponse,
)
async def generate_briefing(
    document_id: int, topic: OwnedTopicDep, db: SessionDep
) -> BriefingGenerateResponse:
    await _ensure_doc_in_topic(db, topic.id, document_id)
    existing = await BriefingAsyncRepository(db).get(document_id)
    if existing and existing.status == "success":
        return BriefingGenerateResponse(document_id=document_id, status="success", message="cached")
    try:
        from app.tasks.intel_tasks import (
            generate_document_briefing_task,
            generate_topic_document_insight_task,
        )

        generate_document_briefing_task.apply_async(
            kwargs=dict(document_id=document_id), queue="intelligence"
        )
        generate_topic_document_insight_task.apply_async(
            kwargs=dict(topic_id=topic.id, document_id=document_id),
            queue="intelligence",
            countdown=10,
        )
    except Exception as exc:
        return BriefingGenerateResponse(
            document_id=document_id, status="failed", message=f"dispatch error: {exc}"
        )
    return BriefingGenerateResponse(document_id=document_id, status="queued")


@router.patch(
    "/topics/{topic_id}/documents/{document_id}/state",
    response_model=UserDocStatePublic,
)
async def patch_user_doc_state(
    document_id: int,
    body: UserDocStateUpdate,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> UserDocStatePublic:
    await _ensure_doc_in_topic(db, topic.id, document_id)
    fields = body.model_dump(exclude_unset=True)
    s = await UserDocStateAsyncRepository(db).upsert(current_user.id, document_id, fields)
    await db.commit()
    return _state_to_public(s)
