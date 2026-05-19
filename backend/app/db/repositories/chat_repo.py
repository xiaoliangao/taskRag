from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import ChatMessage, ChatSession


class ChatRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_session(
        self, *, user_id: int, topic_id: int, title: str, mode: str = "default"
    ) -> ChatSession:
        s = ChatSession(user_id=user_id, topic_id=topic_id, title=title, mode=mode)
        self.db.add(s)
        await self.db.flush()
        return s

    async def get_session(self, session_id: int) -> ChatSession | None:
        return await self.db.get(ChatSession, session_id)

    async def update_session(
        self, session: ChatSession, *, title: str | None = None, mode: str | None = None
    ) -> ChatSession:
        if title is not None:
            session.title = title
        if mode is not None:
            session.mode = mode
        await self.db.flush()
        return session

    async def list_sessions(self, *, user_id: int, topic_id: int) -> Sequence[ChatSession]:
        result = await self.db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id, ChatSession.topic_id == topic_id)
            .order_by(ChatSession.created_at.desc())
        )
        return result.scalars().all()

    async def add_message(
        self,
        *,
        session_id: int,
        role: str,
        content: str,
        citations: list[dict] | None = None,
    ) -> ChatMessage:
        m = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            citations_json=citations or [],
        )
        self.db.add(m)
        await self.db.flush()
        return m

    async def list_messages(self, session_id: int, *, limit: int | None = None) -> Sequence[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def recent_history(self, session_id: int, turns: int) -> Sequence[ChatMessage]:
        """Get the last N user+assistant pairs (turns * 2 messages)."""
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(turns * 2)
        )
        msgs = list(result.scalars().all())
        msgs.reverse()
        return msgs
