"""Method Comparison API (Sprint 4)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUserDep, OwnedTopicDep, SessionDep
from app.core.errors import NotFoundError
from app.db.models.research_ext import ComparisonItem
from app.schemas.research_ext import (
    ComparisonCreate,
    ComparisonItemPublic,
    ComparisonSessionPublic,
    ComparisonSessionSummary,
)
from app.services.comparison_service import (
    ComparisonService,
    get_session,
    list_sessions,
)

router = APIRouter()


async def _to_public(session, db) -> ComparisonSessionPublic:
    items = (
        await db.execute(
            select(ComparisonItem)
            .where(ComparisonItem.comparison_session_id == session.id)
            .order_by(ComparisonItem.order_index.asc())
        )
    ).scalars().all()
    return ComparisonSessionPublic(
        id=session.id,
        topic_id=session.topic_id,
        title=session.title,
        status=session.status,
        result_md=session.result_md,
        result_json=session.result_json or {},
        error_message=session.error_message,
        items=[
            ComparisonItemPublic(
                document_id=it.document_id,
                role=it.role,
                order_index=it.order_index,
            )
            for it in items
        ],
        created_at=session.created_at,
        finished_at=session.finished_at,
    )


@router.post(
    "/topics/{topic_id}/comparisons",
    response_model=ComparisonSessionPublic,
)
async def create_comparison(
    body: ComparisonCreate,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> ComparisonSessionPublic:
    try:
        session = await ComparisonService(db).create(
            user_id=current_user.id,
            topic_id=topic.id,
            title=body.title or "Comparison",
            document_ids=body.document_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return await _to_public(session, db)


@router.get(
    "/topics/{topic_id}/comparisons",
    response_model=list[ComparisonSessionSummary],
)
async def list_comparisons(
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
    limit: int = Query(30, ge=1, le=100),
) -> list[ComparisonSessionSummary]:
    items = await list_sessions(db, current_user.id, topic.id, limit=limit)
    out: list[ComparisonSessionSummary] = []
    for s in items:
        sub = (
            await db.execute(
                select(ComparisonItem.document_id)
                .where(ComparisonItem.comparison_session_id == s.id)
                .order_by(ComparisonItem.order_index.asc())
            )
        ).all()
        out.append(
            ComparisonSessionSummary(
                id=s.id,
                topic_id=s.topic_id,
                title=s.title,
                status=s.status,
                document_ids=[r[0] for r in sub],
                created_at=s.created_at,
                finished_at=s.finished_at,
            )
        )
    return out


@router.get(
    "/topics/{topic_id}/comparisons/{comparison_id}",
    response_model=ComparisonSessionPublic,
)
async def get_comparison(
    comparison_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> ComparisonSessionPublic:
    s = await get_session(db, comparison_id)
    if not s or s.topic_id != topic.id or s.user_id != current_user.id:
        raise NotFoundError("Comparison not found")
    return await _to_public(s, db)


@router.post(
    "/topics/{topic_id}/comparisons/{comparison_id}/generate",
    response_model=ComparisonSessionPublic,
)
async def generate_comparison(
    comparison_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> ComparisonSessionPublic:
    """Queue a generate task (async). Returns immediately with status='pending'.
    Client polls GET /comparisons/{id} until status='success' or 'failed'.
    """
    s = await get_session(db, comparison_id)
    if not s or s.topic_id != topic.id or s.user_id != current_user.id:
        raise NotFoundError("Comparison not found")
    # Mark as pending so UI can show progress while Celery picks it up.
    s.status = "pending"
    s.error_message = None
    await db.flush()
    await db.commit()
    try:
        from app.tasks.research_tasks import run_method_comparison_task

        run_method_comparison_task.apply_async(
            kwargs={"session_id": comparison_id},
            queue="intelligence",
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("comparison_dispatch_failed: %s", exc)
    return await _to_public(s, db)


@router.get(
    "/topics/{topic_id}/comparisons/{comparison_id}/export",
)
async def export_comparison(
    comparison_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
    fmt: str = Query("markdown", alias="format"),
) -> dict:
    s = await get_session(db, comparison_id)
    if not s or s.topic_id != topic.id or s.user_id != current_user.id:
        raise NotFoundError("Comparison not found")
    if fmt == "markdown":
        return {"format": "markdown", "content": s.result_md or ""}
    if fmt == "latex":
        return {"format": "latex", "content": _to_latex(s.result_json or {})}
    raise HTTPException(status_code=400, detail="unsupported format")


def _to_latex(result_json: dict) -> str:
    cols = result_json.get("columns") or []
    rows = result_json.get("rows") or []
    if not cols or not rows:
        return "% empty"
    lines = ["\\begin{tabular}{" + ("l" * len(cols)) + "}", "\\hline"]
    lines.append(" & ".join(c.replace("_", "\\_") for c in cols) + " \\\\\\hline")
    for r in rows:
        cells = []
        for c in cols:
            val = r.get(c, "")
            if not isinstance(val, str):
                val = str(val)
            cells.append(val.replace("&", "\\&").replace("_", "\\_"))
        lines.append(" & ".join(cells) + " \\\\")
    lines.append("\\hline\\end{tabular}")
    return "\n".join(lines)


__all__ = ["router"]
