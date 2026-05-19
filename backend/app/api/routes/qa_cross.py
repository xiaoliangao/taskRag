"""Cross-topic QA API (v1.4 Sprint 7).

POST /api/v1/qa/cross-topic
Body: {topic_ids: [int], question: str, mode?: str}

Security: every topic_id in the request MUST belong to current_user.
Citations include both topic_id and topic_name for UI labelling.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.rag.llm_client import get_llm_client
from app.rag.prompt import NO_CONTEXT_FALLBACK, build_messages
from app.services.qa_cross_service import list_user_topic_ids, retrieve_cross_topic

log = logging.getLogger(__name__)
router = APIRouter()


class CrossTopicQARequest(BaseModel):
    topic_ids: list[int] = Field(default_factory=list, description="Subset of user's owned topics; empty = all")
    question: str = Field(min_length=1, max_length=2000)
    mode: str = Field(default="default", max_length=32)


class CrossTopicCitation(BaseModel):
    topic_id: int | None
    topic_name: str | None
    document_id: int
    chunk_id: int | None
    title: str
    url: str
    source: str
    published_at: str | None
    section_title: str | None
    page_start: int | None
    page_end: int | None
    score: float


class CrossTopicQAResponse(BaseModel):
    answer: str
    citations: list[CrossTopicCitation]
    topics_searched: list[int]


@router.post("/qa/cross-topic", response_model=CrossTopicQAResponse)
async def cross_topic_qa(
    body: CrossTopicQARequest,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> CrossTopicQAResponse:
    owned = await list_user_topic_ids(db, current_user.id)
    if not owned:
        raise HTTPException(status_code=400, detail="You don't own any topics yet")

    if body.topic_ids:
        # ALL requested topic_ids must be owned by caller.
        requested = set(body.topic_ids)
        if not requested.issubset(set(owned)):
            illegal = requested - set(owned)
            raise HTTPException(
                status_code=403,
                detail=f"topic_ids not owned by current user: {sorted(illegal)}",
            )
        scope = sorted(requested)
    else:
        scope = sorted(owned)

    citations = await retrieve_cross_topic(db=db, topic_ids=scope, query=body.question)
    if not citations:
        return CrossTopicQAResponse(answer=NO_CONTEXT_FALLBACK, citations=[], topics_searched=scope)

    citation_dicts = [c.to_dict(drop_text=False) for c in citations]
    messages = build_messages(
        question=body.question,
        chat_history=[],
        citations=citation_dicts,
        chat_mode=body.mode,
    )
    try:
        answer = get_llm_client().complete(messages, feature="cross_topic_qa", max_tokens=1200)
    except Exception as exc:
        log.exception("cross_topic_qa_llm_failed")
        raise HTTPException(status_code=502, detail=f"LLM failed: {exc}") from exc

    public: list[CrossTopicCitation] = []
    for c in citations:
        extra = getattr(c, "_cross_topic", None) or {}
        public.append(
            CrossTopicCitation(
                topic_id=extra.get("topic_id"),
                topic_name=extra.get("topic_name"),
                document_id=c.document_id,
                chunk_id=c.chunk_id,
                title=c.title,
                url=c.url,
                source=c.source,
                published_at=c.published_at.isoformat() if c.published_at else None,
                section_title=c.section_title,
                page_start=c.page_start,
                page_end=c.page_end,
                score=round(c.score, 4),
            )
        )

    return CrossTopicQAResponse(answer=answer, citations=public, topics_searched=scope)


__all__ = ["router"]
