from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.api.deps import CurrentUserDep, OwnedTopicDep, SessionDep, get_owned_chat_session
from app.db.models.chat import ChatSession
from app.db.repositories.chat_repo import ChatRepository
from app.schemas.qa import (
    ChatMessageCreate,
    ChatMessagePublic,
    ChatSessionCreate,
    ChatSessionPublic,
    ChatSessionUpdate,
    QAResponse,
)
from app.services.qa_service import answer_nonstream, answer_stream

router = APIRouter()

OwnedChatDep = Annotated[ChatSession, Depends(get_owned_chat_session)]


@router.post(
    "/topics/{topic_id}/chat/sessions",
    response_model=ChatSessionPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    body: ChatSessionCreate, topic: OwnedTopicDep, db: SessionDep, current_user: CurrentUserDep
) -> ChatSessionPublic:
    s = await ChatRepository(db).create_session(
        user_id=current_user.id, topic_id=topic.id, title=body.title, mode=body.mode or "default"
    )
    await db.commit()
    return ChatSessionPublic.model_validate(s)


@router.patch(
    "/topics/{topic_id}/chat/sessions/{session_id}",
    response_model=ChatSessionPublic,
)
async def update_session(
    body: ChatSessionUpdate,
    chat: OwnedChatDep,
    db: SessionDep,
) -> ChatSessionPublic:
    s = await ChatRepository(db).update_session(chat, title=body.title, mode=body.mode)
    await db.commit()
    return ChatSessionPublic.model_validate(s)


@router.get("/topics/{topic_id}/chat/sessions", response_model=list[ChatSessionPublic])
async def list_sessions(
    topic: OwnedTopicDep, db: SessionDep, current_user: CurrentUserDep
) -> list[ChatSessionPublic]:
    items = await ChatRepository(db).list_sessions(user_id=current_user.id, topic_id=topic.id)
    return [ChatSessionPublic.model_validate(x) for x in items]


@router.get(
    "/topics/{topic_id}/chat/sessions/{session_id}/messages",
    response_model=list[ChatMessagePublic],
)
async def list_messages(
    chat: OwnedChatDep,
    db: SessionDep,
) -> list[ChatMessagePublic]:
    msgs = await ChatRepository(db).list_messages(chat.id)
    return [
        ChatMessagePublic(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            citations=m.citations_json or [],
            created_at=m.created_at,
        )
        for m in msgs
    ]


@router.post(
    "/topics/{topic_id}/chat/sessions/{session_id}/messages",
    response_model=QAResponse,
)
async def post_message(
    body: ChatMessageCreate,
    chat: OwnedChatDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> QAResponse:
    result = await answer_nonstream(db=db, user=current_user, chat=chat, question=body.content)
    return QAResponse(
        message_id=result.message_id,
        content=result.content,
        citations=result.citations,
    )


@router.get("/topics/{topic_id}/chat/sessions/{session_id}/stream")
async def stream_message(
    chat: OwnedChatDep,
    db: SessionDep,
    current_user: CurrentUserDep,
    message: str = Query(..., min_length=1, max_length=4000),
):
    async def event_gen() -> AsyncIterator[dict]:
        try:
            async for evt in answer_stream(
                db=db, user=current_user, chat=chat, question=message
            ):
                yield {
                    "event": evt["event"],
                    "data": json.dumps(evt["data"], ensure_ascii=False),
                }
        except Exception as exc:
            yield {
                "event": "error",
                "data": json.dumps({"code": "INTERNAL_ERROR", "message": str(exc)[:200]}),
            }

    return EventSourceResponse(event_gen())


# ---- v1.5: Conversation Memory list / delete ----


class ChatSummaryPublic(BaseModel):
    id: int
    chat_session_id: int
    summary_md: str
    memory_items: list[dict] = []
    message_count_at_gen: int
    generated_at: datetime


@router.get(
    "/topics/{topic_id}/chat/memory",
    response_model=list[ChatSummaryPublic],
    tags=["memory"],
)
async def list_chat_memory(
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
    limit: int = Query(20, ge=1, le=100),
) -> list[ChatSummaryPublic]:
    from app.db.models.chat import ChatSessionSummary
    from sqlalchemy import select

    rows = (
        await db.execute(
            select(ChatSessionSummary)
            .where(
                ChatSessionSummary.user_id == current_user.id,
                ChatSessionSummary.topic_id == topic.id,
            )
            .order_by(ChatSessionSummary.generated_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        ChatSummaryPublic(
            id=r.id,
            chat_session_id=r.chat_session_id,
            summary_md=r.summary_md,
            memory_items=list(r.memory_items_json or []),
            message_count_at_gen=r.message_count_at_gen,
            generated_at=r.generated_at,
        )
        for r in rows
    ]


@router.delete("/topics/{topic_id}/chat/memory/{summary_id}", tags=["memory"])
async def delete_chat_memory(
    summary_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> dict:
    from app.db.models.chat import ChatSessionSummary

    row = await db.get(ChatSessionSummary, summary_id)
    if not row or row.user_id != current_user.id or row.topic_id != topic.id:
        from app.core.errors import NotFoundError

        raise NotFoundError("summary not found")
    await db.delete(row)
    await db.commit()
    return {"deleted": True, "id": summary_id}
