"""Admin: list / inspect / trigger RAG eval runs (Wave-3.5 Pkg-Eval2-UI).

All routes admin-only. The CLI (`app.eval.run_eval`) remains the canonical
way to run an eval — these endpoints make the same data viewable + triggerable
without shelling into the container.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select

from app.api.deps import CurrentAdminDep, SessionDep
from app.core.errors import NotFoundError
from app.db.models.eval import RagEvalQuestion, RagEvalRun

log = logging.getLogger(__name__)
router = APIRouter()


# ---------- Schemas ----------


class EvalQuestionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    topic_id: int
    question: str
    reference_answer: str | None
    expected_chunk_ids: list[int]
    tag: str | None
    created_at: datetime


class EvalRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    topic_id: int
    label: str
    commit_sha: str | None
    created_at: datetime
    # Top-line numbers pulled out of metrics_json for easy charting.
    recall_at_5: float | None = None
    recall_at_20: float | None = None
    mrr: float | None = None
    n_questions: int = 0


class EvalRunDetail(EvalRunSummary):
    notes: str | None = None
    metrics_json: dict[str, Any] = Field(default_factory=dict)


class TriggerRunRequest(BaseModel):
    topic_id: int
    label: str = Field(default="adhoc", max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    # Opt-in: also generate an answer per question and run the faithfulness
    # judge. Paid (LLM calls per question) so it defaults off.
    run_generation: bool = False


class TriggerRunResponse(BaseModel):
    run_id: int
    label: str
    metrics: dict[str, Any]


# ---------- Helpers ----------


def _summary_from_row(row: RagEvalRun) -> EvalRunSummary:
    m = row.metrics_json or {}
    # `recall@20` is the key; field names can't contain @ so we alias.
    return EvalRunSummary(
        id=row.id,
        topic_id=row.topic_id,
        label=row.label,
        commit_sha=row.commit_sha,
        created_at=row.created_at,
        recall_at_5=m.get("recall@5"),
        recall_at_20=m.get("recall@20"),
        mrr=m.get("mrr"),
        n_questions=int(m.get("n_questions") or 0),
    )


# ---------- Routes ----------


@router.get("/runs", response_model=list[EvalRunSummary])
async def list_runs(
    db: SessionDep,
    _admin: CurrentAdminDep,
    topic_id: int | None = None,
    limit: int = 50,
) -> list[EvalRunSummary]:
    stmt = select(RagEvalRun)
    if topic_id is not None:
        stmt = stmt.where(RagEvalRun.topic_id == topic_id)
    stmt = stmt.order_by(desc(RagEvalRun.id)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [_summary_from_row(r) for r in rows]


@router.get("/runs/{run_id}", response_model=EvalRunDetail)
async def get_run(
    run_id: int, db: SessionDep, _admin: CurrentAdminDep
) -> EvalRunDetail:
    row = await db.get(RagEvalRun, run_id)
    if not row:
        raise NotFoundError("Run not found")
    m = row.metrics_json or {}
    return EvalRunDetail(
        id=row.id,
        topic_id=row.topic_id,
        label=row.label,
        commit_sha=row.commit_sha,
        created_at=row.created_at,
        notes=row.notes,
        metrics_json=m,
        recall_at_5=m.get("recall@5"),
        recall_at_20=m.get("recall@20"),
        mrr=m.get("mrr"),
        n_questions=int(m.get("n_questions") or 0),
    )


@router.get("/questions", response_model=list[EvalQuestionPublic])
async def list_questions(
    db: SessionDep,
    _admin: CurrentAdminDep,
    topic_id: int | None = None,
) -> list[EvalQuestionPublic]:
    stmt = select(RagEvalQuestion)
    if topic_id is not None:
        stmt = stmt.where(RagEvalQuestion.topic_id == topic_id)
    stmt = stmt.order_by(RagEvalQuestion.id.asc())
    rows = (await db.execute(stmt)).scalars().all()
    return [EvalQuestionPublic.model_validate(r) for r in rows]


@router.post(
    "/runs",
    response_model=TriggerRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_run(
    body: TriggerRunRequest, db: SessionDep, _admin: CurrentAdminDep
) -> TriggerRunResponse:
    """Run the eval suite synchronously against `topic_id` and persist a run row.

    Eval takes ~5-30s for retrieval-only. With `run_generation` it also runs a
    generation + faithfulness judge per question (slower + paid), recorded in a
    separate `faithfulness` block of metrics_json. For very large sets this
    should move to a Celery task — but until then, blocking the admin request is
    fine: it's an admin tool, not a user-facing path.
    """
    # Import locally to avoid pulling the eval module at app import time.
    from app.eval.run_eval import _current_commit_sha, _evaluate

    metrics = await _evaluate(db, body.topic_id, judge=body.run_generation)
    row = RagEvalRun(
        topic_id=body.topic_id,
        label=body.label,
        commit_sha=_current_commit_sha(),
        metrics_json=metrics,
        notes=body.notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    log.info(
        "admin_eval triggered: run_id=%s topic=%s recall@5=%s mrr=%s",
        row.id, row.topic_id, metrics.get("recall@5"), metrics.get("mrr"),
    )
    return TriggerRunResponse(run_id=row.id, label=row.label, metrics=metrics)


__all__ = ["router"]
