from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_documents_source_external"),
        Index("idx_documents_source_published", "source", "published_at"),
        Index("idx_documents_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    parse_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_doc_index"),
        Index("idx_chunks_document_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Nullable: parents don't get a vector since we only embed children.
    vector_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, unique=True
    )
    # Self-referential parent. Children point to a parent row; parents have
    # parent_id IS NULL and is_parent=true.
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    is_parent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # LLM-generated situating context (Wave-3 Pkg-CR). For child chunks, this
    # is the one-line "what does this section discuss" summary derived from
    # the parent; we prepend it to chunk.text before embedding so the vector
    # carries the surrounding section's framing. NULL for parents and for
    # legacy chunks ingested before this feature shipped.
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TopicDocument(Base):
    __tablename__ = "topic_documents"
    __table_args__ = (
        Index("idx_topic_documents_document_id", "document_id"),
    )

    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    matched_keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by_task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
