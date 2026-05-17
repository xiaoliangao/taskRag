from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.models.chat import ChatSession
from app.db.models.topic import Topic
from app.db.models.user import User
from app.db.repositories.chat_repo import ChatRepository
from app.db.repositories.topic_repo import TopicRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import get_db


SessionDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise UnauthorizedError("Invalid token") from exc
    if payload.get("type") != "access":
        raise UnauthorizedError("Wrong token type")
    user_id_raw = payload.get("sub")
    if not user_id_raw:
        raise UnauthorizedError("Token missing subject")
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Token subject invalid") from exc

    user = await UserRepository(db).get_by_id(user_id)
    if not user:
        raise UnauthorizedError("User no longer exists")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_owned_topic(
    topic_id: int,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> Topic:
    topic = await TopicRepository(db).get_by_id(topic_id)
    if not topic or topic.user_id != current_user.id:
        # Hide existence of others' resources
        raise NotFoundError("Topic not found")
    return topic


OwnedTopicDep = Annotated[Topic, Depends(get_owned_topic)]


async def get_owned_chat_session(
    session_id: int,
    db: SessionDep,
    topic: OwnedTopicDep,
    current_user: CurrentUserDep,
) -> ChatSession:
    chat = await ChatRepository(db).get_session(session_id)
    if not chat or chat.user_id != current_user.id or chat.topic_id != topic.id:
        raise NotFoundError("Chat session not found")
    return chat
