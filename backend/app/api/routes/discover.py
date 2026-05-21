"""Global paper discovery: ad-hoc search across sources, then ingest into a
chosen (or freshly created) topic.

Differs from `/topics/{tid}/search-preview`:
- Keywords come from the request, not a saved topic
- No "already_in_topic" annotation (no topic context until ingest time)
- A single ingest call accepts either an existing topic_id OR a new_topic_name
  (we create the topic on the fly), then dispatches the same Celery pipeline
  as the per-topic manual collect.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.core.config import get_settings
from app.core.constants import CollectionTrigger
from app.core.errors import NotFoundError, ValidationError
from app.db.repositories.task_repo import CollectionTaskRepository
from app.db.repositories.topic_repo import TopicRepository
from app.schemas.picker import PreviewItem
from app.schemas.topic import TopicCreate
from app.services.discover_service import discover_search
from app.services.topic_service import TopicService

log = logging.getLogger(__name__)
router = APIRouter()


# Only collectors that implement an ad-hoc `.search(keywords, since, max_results)`
# belong here. Upload sources (PDF / URL) and feed sources (RSS, github watch)
# don't run query-style searches.
_SEARCHABLE_SOURCES = ("arxiv", "openalex", "semantic_scholar")


def _has_cjk(text: str) -> bool:
    """True if the query contains any CJK character. arxiv's full-text search
    only indexes English titles/abstracts; querying it with Chinese wastes the
    35s timeout, so we deprioritise it (run OpenAlex / SS first) when CJK is
    present."""
    return any("一" <= ch <= "鿿" for ch in (text or ""))


class DiscoverSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    sources: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=50)
    days: int | None = Field(default=None, ge=1, le=3650)


class DiscoverSearchResponse(BaseModel):
    items: list[PreviewItem]
    rate_limited_sources: list[str]
    sources_queried: list[str]


class DiscoverIngestRequest(BaseModel):
    picks: list[PreviewItem] = Field(min_length=1, max_length=50)
    # Pick exactly one of the two:
    topic_id: int | None = None
    new_topic_name: str | None = Field(default=None, min_length=1, max_length=80)


class DiscoverIngestResponse(BaseModel):
    topic_id: int
    topic_name: str
    task_id: int
    count: int
    status: str
    created_topic: bool


@router.post("/search", response_model=DiscoverSearchResponse)
async def discover_search_route(
    body: DiscoverSearchRequest, _user: CurrentUserDep
) -> DiscoverSearchResponse:
    keywords = [k.strip() for k in body.query.split(",") if k.strip()] or [body.query.strip()]
    requested = [s for s in body.sources if s in _SEARCHABLE_SOURCES]
    if requested:
        ordered_sources = requested
    elif _has_cjk(body.query):
        # CJK query: skip arxiv direct (English-only full-text → 35s timeout
        # for nothing). OpenAlex/SS index DOI metadata covering Chinese-titled
        # papers; arxiv preprints that match still surface via OpenAlex's
        # arxiv_id fallback in the OpenAlex collector.
        ordered_sources = ["openalex", "semantic_scholar"]
    else:
        ordered_sources = list(_SEARCHABLE_SOURCES)

    docs, rate_limited = discover_search(
        keywords=keywords,
        sources=ordered_sources,
        limit=body.limit,
        days=body.days,
    )
    items = [
        PreviewItem(
            source=d.source,
            external_id=d.external_id,
            title=d.title,
            authors=d.authors,
            published_at=d.published_at,
            url=d.url,
            abstract=d.abstract,
            raw_content_url=d.raw_content_url,
            matched_keyword=d.matched_keyword,
            metadata=d.metadata,
            already_in_topic=False,
        )
        for d in docs
    ]
    return DiscoverSearchResponse(
        items=items,
        rate_limited_sources=rate_limited,
        sources_queried=ordered_sources,
    )


@router.post(
    "/ingest", response_model=DiscoverIngestResponse, status_code=status.HTTP_201_CREATED
)
async def discover_ingest_route(
    body: DiscoverIngestRequest,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> DiscoverIngestResponse:
    if (body.topic_id is None) == (body.new_topic_name is None):
        raise ValidationError("provide exactly one of topic_id or new_topic_name")

    topics = TopicService(db)
    created = False
    if body.new_topic_name:
        # Seed the topic with the picks' sources + matched keywords so future
        # scheduled collects have something sensible. Schedule defaults are fine
        # — user can edit later.
        srcs = sorted({p.source for p in body.picks}) or ["arxiv"]
        kws = sorted({p.matched_keyword for p in body.picks if p.matched_keyword})
        if not kws:
            kws = [body.new_topic_name.strip()]
        topic = await topics.create(
            current_user,
            TopicCreate(
                name=body.new_topic_name.strip(),
                description="自动建立(来自全局检索)",
                keywords=kws[:10],
                sources=srcs,
                # Don't auto-schedule by default — user explicitly picked specific
                # papers; they may not want this topic to keep refilling.
                enabled=False,
            ),
        )
        created = True
    else:
        topic = await TopicRepository(db).get_by_id(body.topic_id or 0)
        if not topic or topic.user_id != current_user.id:
            raise NotFoundError("Topic not found")

    repo = CollectionTaskRepository(db)
    task = await repo.create(
        topic_id=topic.id,
        source="manual_pick",
        trigger=CollectionTrigger.MANUAL.value,
        requested_by_user_id=current_user.id,
    )
    await db.commit()

    try:
        from app.tasks.collect_tasks import ingest_picked_documents_task

        picks_payload = [p.model_dump(mode="json") for p in body.picks]
        ingest_picked_documents_task.apply_async(
            kwargs=dict(
                topic_id=topic.id,
                picks=picks_payload,
                collection_task_id=task.id,
                requested_by_user_id=current_user.id,
            ),
            queue="urgent",
        )
    except Exception as exc:
        log.warning("discover ingest dispatch failed: %s", exc)

    return DiscoverIngestResponse(
        topic_id=topic.id,
        topic_name=topic.name,
        task_id=task.id,
        count=len(body.picks),
        status="queued",
        created_topic=created,
    )
