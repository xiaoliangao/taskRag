"""Concept Glossary API (Sprint 5 MVP)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import OwnedTopicDep, SessionDep
from app.schemas.research_ext import GlossaryGenerateResponse, GlossaryTermPublic
from app.services.glossary_service import (
    generate_glossary_for_topic,
    list_glossary,
)

router = APIRouter()


@router.get(
    "/topics/{topic_id}/glossary",
    response_model=list[GlossaryTermPublic],
)
async def list_glossary_route(
    topic: OwnedTopicDep,
    db: SessionDep,
    limit: int = Query(80, ge=1, le=200),
) -> list[GlossaryTermPublic]:
    rows = await list_glossary(db, topic.id, limit=limit)
    return [
        GlossaryTermPublic(
            id=r.id,
            term=r.term,
            normalized_term=r.normalized_term,
            definition=r.definition,
            representative_document_ids=list(r.representative_document_ids or []),
            confidence=r.confidence,
        )
        for r in rows
    ]


@router.post(
    "/topics/{topic_id}/glossary/generate",
    response_model=GlossaryGenerateResponse,
)
async def generate_glossary_route(
    topic: OwnedTopicDep,
    db: SessionDep,
    limit_terms: int = Query(15, ge=1, le=40),
) -> GlossaryGenerateResponse:
    stats = await generate_glossary_for_topic(db, topic.id, limit_terms=limit_terms)
    await db.commit()
    return GlossaryGenerateResponse(status="success", **stats)


__all__ = ["router"]
