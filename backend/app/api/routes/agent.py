"""Agent QA route (v1.5 B-3).

POST /api/v1/qa/agent
Body: {question, topic_ids?: [int], max_steps?: int}
Returns: { final_answer, steps, error }
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.services.agent import run_agent
from app.services.qa_cross_service import list_user_topic_ids

log = logging.getLogger(__name__)
router = APIRouter()


class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    topic_ids: list[int] = Field(default_factory=list)
    max_steps: int = Field(default=5, ge=1, le=8)


class AgentStepPublic(BaseModel):
    role: str
    content: str = ""
    tool: str | None = None
    args: dict | None = None


class AgentResponse(BaseModel):
    final_answer: str
    steps: list[AgentStepPublic]
    error: str | None = None
    topics_searched: list[int]


@router.post("/qa/agent", response_model=AgentResponse, tags=["agent"])
async def run_qa_agent(
    body: AgentRequest,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> AgentResponse:
    owned = await list_user_topic_ids(db, current_user.id)
    if not owned:
        raise HTTPException(status_code=400, detail="You don't own any topics yet")

    if body.topic_ids:
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

    trace = await run_agent(
        db=db,
        question=body.question,
        owned_topic_ids=scope,
        max_steps=body.max_steps,
    )
    d = trace.to_dict()
    return AgentResponse(
        final_answer=d["final_answer"],
        steps=[AgentStepPublic(**s) for s in d["steps"]],
        error=d["error"],
        topics_searched=scope,
    )


__all__ = ["router"]
