"""Research Notes API + Pin from chat."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, OwnedTopicDep, SessionDep
from app.core.errors import NotFoundError
from app.db.repositories.chat_repo import ChatRepository
from app.db.repositories.intel_repo import NotesAsyncRepository

router = APIRouter()


class NoteCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content_md: str = Field(min_length=1, max_length=20_000)
    source_type: str = Field(default="manual")
    source_id: int | None = None
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False


class NoteUpdate(BaseModel):
    title: str | None = None
    content_md: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None


class NotePublic(BaseModel):
    id: int
    topic_id: int
    source_type: str
    source_id: int | None
    title: str | None
    content_md: str
    tags: list[str]
    pinned: bool
    created_at: str
    updated_at: str


def _to_public(n) -> NotePublic:
    return NotePublic(
        id=n.id,
        topic_id=n.topic_id,
        source_type=n.source_type,
        source_id=n.source_id,
        title=n.title,
        content_md=n.content_md,
        tags=list(n.tags or []),
        pinned=n.pinned,
        created_at=n.created_at.isoformat(),
        updated_at=n.updated_at.isoformat(),
    )


@router.get("/topics/{topic_id}/notes", response_model=list[NotePublic])
async def list_notes(
    topic: OwnedTopicDep, db: SessionDep, current_user: CurrentUserDep
) -> list[NotePublic]:
    items = await NotesAsyncRepository(db).list_for_topic(current_user.id, topic.id)
    return [_to_public(n) for n in items]


@router.post("/topics/{topic_id}/notes", response_model=NotePublic)
async def create_note(
    body: NoteCreate, topic: OwnedTopicDep, db: SessionDep, current_user: CurrentUserDep
) -> NotePublic:
    n = await NotesAsyncRepository(db).create(
        user_id=current_user.id,
        topic_id=topic.id,
        source_type=body.source_type,
        source_id=body.source_id,
        title=body.title,
        content_md=body.content_md,
        tags=body.tags,
        pinned=body.pinned,
    )
    await db.commit()
    return _to_public(n)


@router.patch("/topics/{topic_id}/notes/{note_id}", response_model=NotePublic)
async def update_note(
    note_id: int,
    body: NoteUpdate,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> NotePublic:
    repo = NotesAsyncRepository(db)
    n = await repo.get(note_id)
    if not n or n.user_id != current_user.id or n.topic_id != topic.id:
        raise NotFoundError("Note not found")
    fields = body.model_dump(exclude_unset=True)
    n = await repo.update(n, fields)
    await db.commit()
    return _to_public(n)


@router.delete("/topics/{topic_id}/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: int, topic: OwnedTopicDep, db: SessionDep, current_user: CurrentUserDep
):
    repo = NotesAsyncRepository(db)
    n = await repo.get(note_id)
    if not n or n.user_id != current_user.id or n.topic_id != topic.id:
        raise NotFoundError("Note not found")
    await repo.delete(n)
    await db.commit()


@router.post(
    "/topics/{topic_id}/chat/messages/{message_id}/pin",
    response_model=NotePublic,
)
async def pin_chat_message(
    message_id: int,
    topic: OwnedTopicDep,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> NotePublic:
    """Convert an assistant chat message into a pinned research note."""
    from sqlalchemy import select
    from app.db.models.chat import ChatMessage, ChatSession

    r = await db.execute(
        select(ChatMessage, ChatSession)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.id == message_id)
    )
    row = r.first()
    if not row:
        raise NotFoundError("Message not found")
    msg, sess = row
    if sess.user_id != current_user.id or sess.topic_id != topic.id:
        raise NotFoundError("Message not found")

    title = (msg.content or "").splitlines()[0][:80] if msg.content else None
    n = await NotesAsyncRepository(db).create(
        user_id=current_user.id,
        topic_id=topic.id,
        source_type="chat_pin",
        source_id=msg.id,
        title=title,
        content_md=msg.content,
        tags=["chat"],
        pinned=True,
    )
    await db.commit()
    return _to_public(n)
