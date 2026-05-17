"""Research Pulse API."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import OwnedTopicDep, SessionDep
from app.core.errors import NotFoundError
from app.db.repositories.intel_repo import PulseAsyncRepository

router = APIRouter()


class PulsePublic(BaseModel):
    id: int
    topic_id: int
    pulse_date: str
    status: str
    title: str | None
    summary_md: str | None
    highlights: list
    new_documents: list
    important_documents: list
    emerging_keywords: list
    suggested_actions: list
    citations: list
    generated_at: str | None


def _to_public(p) -> PulsePublic:
    return PulsePublic(
        id=p.id,
        topic_id=p.topic_id,
        pulse_date=p.pulse_date.date().isoformat() if p.pulse_date else "",
        status=p.status,
        title=p.title,
        summary_md=p.summary_md,
        highlights=p.highlights or [],
        new_documents=p.new_documents or [],
        important_documents=p.important_documents or [],
        emerging_keywords=p.emerging_keywords or [],
        suggested_actions=p.suggested_actions or [],
        citations=p.citations_json or [],
        generated_at=p.generated_at.isoformat() if p.generated_at else None,
    )


@router.get("/topics/{topic_id}/pulses", response_model=list[PulsePublic])
async def list_pulses(topic: OwnedTopicDep, db: SessionDep) -> list[PulsePublic]:
    items = await PulseAsyncRepository(db).list_for_topic(topic.id)
    return [_to_public(p) for p in items]


@router.get("/topics/{topic_id}/pulses/latest", response_model=PulsePublic | None)
async def get_latest(topic: OwnedTopicDep, db: SessionDep) -> PulsePublic | None:
    p = await PulseAsyncRepository(db).get_latest(topic.id)
    return _to_public(p) if p else None


@router.get("/topics/{topic_id}/pulses/{pulse_id}", response_model=PulsePublic)
async def get_pulse(pulse_id: int, topic: OwnedTopicDep, db: SessionDep) -> PulsePublic:
    p = await PulseAsyncRepository(db).get_by_id(pulse_id)
    if not p or p.topic_id != topic.id:
        raise NotFoundError("Pulse not found")
    return _to_public(p)


@router.post("/topics/{topic_id}/pulses/generate")
async def generate_pulse(topic: OwnedTopicDep) -> dict:
    try:
        from app.tasks.intel_tasks import generate_topic_pulse_task

        generate_topic_pulse_task.apply_async(
            kwargs=dict(topic_id=topic.id, force=True), queue="intelligence"
        )
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}
    return {"status": "queued", "topic_id": topic.id}
