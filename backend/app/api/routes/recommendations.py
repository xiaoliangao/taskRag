"""GET /users/me/recommendations — "For You" feed driven by user favorites.

The heavy lifting (Qdrant scroll + LLM calls + discover_search) is synchronous
and IO/CPU heavy, so we run it in a threadpool with the sync sessionmaker
rather than blocking the event loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUserDep
from app.db.session import get_sync_sessionmaker
from app.services.recommendation_service import get_recommendations_for_user

log = logging.getLogger(__name__)
router = APIRouter()


class RecommendedItemPublic(BaseModel):
    source: str
    external_id: str
    title: str
    authors: list[str]
    published_at: str | None
    url: str | None
    abstract: str | None
    score: float | None
    rationale: str | None
    in_corpus: bool
    document_id: int | None
    topic_ids: list[int]


class RecommendationResponse(BaseModel):
    items: list[RecommendedItemPublic]
    favorites_count: int
    generated_at: str
    cached: bool


@router.get("/users/me/recommendations", response_model=RecommendationResponse)
async def my_recommendations(
    current_user: CurrentUserDep,
    limit: int = Query(10, ge=1, le=30),
    refresh: bool = Query(False),
) -> RecommendationResponse:
    def _work() -> dict[str, Any]:
        SessionLocal = get_sync_sessionmaker()
        with SessionLocal() as db:
            return get_recommendations_for_user(
                db, user_id=current_user.id, limit=limit, refresh=refresh
            )

    payload = await asyncio.to_thread(_work)
    return RecommendationResponse(
        items=[RecommendedItemPublic(**it) for it in payload["items"]],
        favorites_count=payload["favorites_count"],
        generated_at=payload["generated_at"],
        cached=bool(payload.get("cached", False)),
    )
