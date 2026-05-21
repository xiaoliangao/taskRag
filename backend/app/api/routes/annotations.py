"""PDF annotation CRUD (Pkg-P stage 1).

Endpoints live under the same `/topics/{tid}/documents/{did}` prefix as the
PDF stream, so permission is gated by `OwnedTopicDep` + a check that the
document is linked to that topic.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, OwnedTopicDep, SessionDep
from app.core.errors import ForbiddenError, NotFoundError
from app.db.models.annotation import Annotation
from app.db.models.document import Chunk, TopicDocument
from app.db.models.intel import ResearchNote
from app.schemas.annotation import (
    AnnotationCreate,
    AnnotationPatch,
    AnnotationPublic,
)

log = logging.getLogger(__name__)
router = APIRouter()


async def _assert_doc_in_topic(db, topic_id: int, document_id: int) -> None:
    r = await db.execute(
        select(TopicDocument.document_id).where(
            TopicDocument.topic_id == topic_id,
            TopicDocument.document_id == document_id,
        )
    )
    if r.scalar_one_or_none() is None:
        raise NotFoundError("Document not in this topic")


async def _guess_chunk_id(
    db, document_id: int, page_number: int, selected_text: str
) -> int | None:
    """Return the chunk_id whose page range covers `page_number` and whose text
    contains a snippet of `selected_text`. Best-effort; returns None on ties or
    misses so RAG can still ignore the annotation gracefully."""
    snippet = (selected_text or "").strip()[:120]
    if not snippet:
        return None
    rows = await db.execute(
        select(Chunk.id, Chunk.text)
        .where(
            Chunk.document_id == document_id,
            (Chunk.page_start.is_(None)) | (Chunk.page_start <= page_number),
            (Chunk.page_end.is_(None)) | (Chunk.page_end >= page_number),
        )
        .order_by(Chunk.chunk_index.asc())
    )
    candidates = [(cid, txt or "") for cid, txt in rows.all()]
    matches = [cid for cid, txt in candidates if snippet[:40] and snippet[:40] in txt]
    if len(matches) == 1:
        return int(matches[0])
    return None


@router.get(
    "/topics/{topic_id}/documents/{document_id}/annotations",
    response_model=list[AnnotationPublic],
)
async def list_annotations(
    document_id: int,
    db: SessionDep,
    topic: OwnedTopicDep,
    current_user: CurrentUserDep,
) -> list[AnnotationPublic]:
    await _assert_doc_in_topic(db, topic.id, document_id)
    rows = await db.execute(
        select(Annotation)
        .where(
            Annotation.user_id == current_user.id,
            Annotation.topic_id == topic.id,
            Annotation.document_id == document_id,
        )
        .order_by(Annotation.page_number.asc(), Annotation.created_at.asc())
    )
    return [AnnotationPublic.model_validate(a) for a in rows.scalars().all()]


@router.post(
    "/topics/{topic_id}/documents/{document_id}/annotations",
    response_model=AnnotationPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_annotation(
    document_id: int,
    body: AnnotationCreate,
    db: SessionDep,
    topic: OwnedTopicDep,
    current_user: CurrentUserDep,
) -> AnnotationPublic:
    await _assert_doc_in_topic(db, topic.id, document_id)

    chunk_id = await _guess_chunk_id(
        db, document_id, body.page_number, body.selected_text
    )

    ann = Annotation(
        user_id=current_user.id,
        document_id=document_id,
        topic_id=topic.id,
        chunk_id=chunk_id,
        page_number=body.page_number,
        kind=body.kind,
        color=body.color,
        selected_text=body.selected_text,
        rects=[r.model_dump() for r in body.rects],
        comment_md=body.comment_md,
    )
    db.add(ann)
    await db.flush()

    if body.save_as_note:
        # Quote the selection, append optional comment, drop into research_notes.
        body_md = f"> {body.selected_text.strip()}"
        if body.comment_md:
            body_md += f"\n\n{body.comment_md.strip()}"
        note = ResearchNote(
            user_id=current_user.id,
            topic_id=topic.id,
            source_type="annotation",
            source_id=ann.id,
            title=None,
            content_md=body_md,
            tags=["pdf"],
            pinned=False,
        )
        db.add(note)
        await db.flush()
        ann.note_id = note.id

    await db.commit()
    await db.refresh(ann)
    return AnnotationPublic.model_validate(ann)


@router.patch(
    "/topics/{topic_id}/documents/{document_id}/annotations/{annotation_id}",
    response_model=AnnotationPublic,
)
async def patch_annotation(
    document_id: int,
    annotation_id: int,
    body: AnnotationPatch,
    db: SessionDep,
    topic: OwnedTopicDep,
    current_user: CurrentUserDep,
) -> AnnotationPublic:
    ann = await db.get(Annotation, annotation_id)
    if not ann or ann.document_id != document_id or ann.topic_id != topic.id:
        raise NotFoundError("Annotation not found")
    if ann.user_id != current_user.id:
        raise ForbiddenError("Not your annotation")
    if body.color is not None:
        ann.color = body.color
    if body.kind is not None:
        ann.kind = body.kind
    if body.comment_md is not None:
        ann.comment_md = body.comment_md
    await db.commit()
    await db.refresh(ann)
    return AnnotationPublic.model_validate(ann)


@router.delete(
    "/topics/{topic_id}/documents/{document_id}/annotations/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_annotation(
    document_id: int,
    annotation_id: int,
    db: SessionDep,
    topic: OwnedTopicDep,
    current_user: CurrentUserDep,
) -> Response:
    ann = await db.get(Annotation, annotation_id)
    if not ann or ann.document_id != document_id or ann.topic_id != topic.id:
        raise NotFoundError("Annotation not found")
    if ann.user_id != current_user.id:
        raise ForbiddenError("Not your annotation")
    await db.delete(ann)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
