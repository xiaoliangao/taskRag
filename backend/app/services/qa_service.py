from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import ChatRole
from app.db.models.chat import ChatSession
from app.db.models.user import User
from app.db.repositories.chat_repo import ChatRepository
from app.rag.llm_client import get_llm_client
from app.rag.prompt import NO_CONTEXT_FALLBACK, build_messages
from app.rag.retriever import Citation, retrieve_for_topic

log = logging.getLogger(__name__)


@dataclass
class QAResult:
    message_id: int
    content: str
    citations: list[dict]


def _llm_for_user(user: User):
    s = get_settings()
    settings_json = user.settings_json or {}
    provider = settings_json.get("preferred_llm_provider") or s.llm_provider
    model = settings_json.get("preferred_llm_model") or s.llm_model
    return get_llm_client(provider, model)


def _history(messages: Sequence) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]


async def _gather_context(
    db: AsyncSession,
    *,
    topic_id: int,
    question: str,
) -> tuple[list[Citation], list[dict]]:
    citations = await retrieve_for_topic(db=db, topic_id=topic_id, query=question)
    citation_dicts = [c.to_dict(drop_text=False) for c in citations]
    return citations, citation_dicts


async def _gather_pinned_notes(db: AsyncSession, user_id: int, topic_id: int, limit: int = 5) -> list[dict]:
    try:
        from app.db.repositories.intel_repo import NotesAsyncRepository

        notes = await NotesAsyncRepository(db).list_recent_pinned(user_id, topic_id, limit=limit)
        return [
            {
                "title": n.title or "(笔记)",
                "content": n.content_md[:800],
                "source_type": n.source_type,
            }
            for n in notes
        ]
    except Exception:
        return []


async def answer_nonstream(
    *,
    db: AsyncSession,
    user: User,
    chat: ChatSession,
    question: str,
) -> QAResult:
    settings = get_settings()
    chats = ChatRepository(db)
    # Persist user message
    user_msg = await chats.add_message(session_id=chat.id, role=ChatRole.USER.value, content=question)
    await db.commit()

    history_msgs = await chats.recent_history(chat.id, settings.history_turns)
    # Exclude the just-added user message from history (it's already in question)
    history = _history([m for m in history_msgs if m.id != user_msg.id])

    citations, citation_dicts = await _gather_context(db, topic_id=chat.topic_id, question=question)
    if not citations:
        assistant_msg = await chats.add_message(
            session_id=chat.id,
            role=ChatRole.ASSISTANT.value,
            content=NO_CONTEXT_FALLBACK,
            citations=[],
        )
        await db.commit()
        return QAResult(message_id=assistant_msg.id, content=NO_CONTEXT_FALLBACK, citations=[])

    pinned = await _gather_pinned_notes(db, user.id, chat.topic_id)
    messages = build_messages(
        question=question,
        chat_history=history,
        citations=citation_dicts,
        pinned_notes=pinned,
        chat_mode=getattr(chat, "mode", None),
    )
    llm = _llm_for_user(user)
    content = llm.complete(messages)

    public_citations = [c.to_dict(drop_text=True) for c in citations]
    assistant_msg = await chats.add_message(
        session_id=chat.id,
        role=ChatRole.ASSISTANT.value,
        content=content,
        citations=public_citations,
    )
    await db.commit()
    return QAResult(message_id=assistant_msg.id, content=content, citations=public_citations)


async def answer_stream(
    *,
    db: AsyncSession,
    user: User,
    chat: ChatSession,
    question: str,
) -> AsyncIterator[dict]:
    """Yields events: {"event": "token"|"citations"|"done"|"error", "data": {...}}"""
    settings = get_settings()
    chats = ChatRepository(db)

    user_msg = await chats.add_message(session_id=chat.id, role=ChatRole.USER.value, content=question)
    await db.commit()

    history_msgs = await chats.recent_history(chat.id, settings.history_turns)
    history = _history([m for m in history_msgs if m.id != user_msg.id])

    citations, citation_dicts = await _gather_context(db, topic_id=chat.topic_id, question=question)
    public_citations = [c.to_dict(drop_text=True) for c in citations]
    yield {"event": "citations", "data": {"items": public_citations}}

    if not citations:
        assistant_msg = await chats.add_message(
            session_id=chat.id,
            role=ChatRole.ASSISTANT.value,
            content=NO_CONTEXT_FALLBACK,
            citations=[],
        )
        await db.commit()
        yield {"event": "token", "data": {"text": NO_CONTEXT_FALLBACK}}
        yield {"event": "done", "data": {"message_id": assistant_msg.id}}
        return

    pinned = await _gather_pinned_notes(db, user.id, chat.topic_id)
    messages = build_messages(
        question=question,
        chat_history=history,
        citations=citation_dicts,
        pinned_notes=pinned,
        chat_mode=getattr(chat, "mode", None),
    )
    llm = _llm_for_user(user)

    buffer: list[str] = []
    try:
        # OpenAI client.stream is a sync iterator; iterate in a thread-friendly manner.
        # FastAPI's StreamingResponse can consume an async generator that yields strings.
        for token in llm.stream(messages):
            buffer.append(token)
            yield {"event": "token", "data": {"text": token}}
    except Exception as exc:
        log.exception("LLM stream error: %s", exc)
        yield {"event": "error", "data": {"code": "UPSTREAM_ERROR", "message": str(exc)[:200]}}
        return

    final_content = "".join(buffer).strip()
    assistant_msg = await chats.add_message(
        session_id=chat.id,
        role=ChatRole.ASSISTANT.value,
        content=final_content,
        citations=public_citations,
    )
    await db.commit()
    yield {"event": "done", "data": {"message_id": assistant_msg.id}}
