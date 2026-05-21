from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Annotation(Base, TimestampMixin):
    """User-created PDF annotation: highlight | comment | note.

    Coordinates are stored in PDF page space (origin bottom-left, points) so
    the renderer can re-project to any zoom level without drift. `rects` is a
    list of `{x, y, w, h}` — multiple rects support multi-line / multi-column
    selections within a single page.

    `chunk_id` is the chunk whose text overlaps the selection; populated on
    create when we can find a unique match, otherwise NULL. Lets future RAG
    weight "user-marked" chunks.

    `note_id` is set when the user chose "save as note" on create; deleting
    the annotation does NOT delete the note (ON DELETE SET NULL).
    """

    __tablename__ = "annotations"
    __table_args__ = (
        Index("idx_annotations_doc_page", "document_id", "page_number"),
        Index("idx_annotations_user_topic", "user_id", "topic_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str] = mapped_column(Text, nullable=False, default="#fff59d")
    selected_text: Mapped[str] = mapped_column(Text, nullable=False)
    rects: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    comment_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("research_notes.id", ondelete="SET NULL"), nullable=True
    )
