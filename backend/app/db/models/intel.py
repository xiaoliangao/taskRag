"""Models added in v1.1+ (Research Intelligence Layer)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


# --- Sprint 1: Briefing / Insight / User state ---

class DocumentBriefing(Base, TimestampMixin):
    __tablename__ = "document_briefings"
    __table_args__ = (
        UniqueConstraint("document_id", "language", name="uq_doc_briefing_doc_lang"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="zh-CN")

    one_sentence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    contributions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    experiments: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    limitations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    datasets: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    metrics: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    code_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    code_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    reading_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_chunk_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    model_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TopicDocumentInsight(Base, TimestampMixin):
    __tablename__ = "topic_document_insights"
    __table_args__ = (
        UniqueConstraint("topic_id", "document_id", name="uq_topic_doc_insight"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reading_priority: Mapped[str | None] = mapped_column(Text, nullable=True)  # high/medium/low
    tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    why_read: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserDocumentState(Base, TimestampMixin):
    __tablename__ = "user_document_states"
    __table_args__ = (
        UniqueConstraint("user_id", "document_id", name="uq_user_doc_state"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="unread")  # unread/reading/read/archived
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    personal_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Sprint 2: Research Pulse ---

class TopicPulse(Base, TimestampMixin):
    __tablename__ = "topic_pulses"
    __table_args__ = (
        UniqueConstraint("topic_id", "pulse_date", name="uq_topic_pulse_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pulse_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    highlights: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    new_documents: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    important_documents: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    emerging_keywords: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    suggested_actions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    citations_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    model_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Sprint 3: Reading Path ---

class ReadingPath(Base, TimestampMixin):
    __tablename__ = "reading_paths"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    scope: Mapped[str] = mapped_column(Text, nullable=False, server_default="topic")
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReadingPathItem(Base):
    __tablename__ = "reading_path_items"
    __table_args__ = (
        UniqueConstraint("reading_path_id", "document_id", name="uq_rp_item_doc"),
        Index("idx_rp_item_order", "reading_path_id", "order_index"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reading_path_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reading_paths.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prerequisite_document_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --- Sprint 4: Research Insights + Notes ---

class ResearchInsight(Base, TimestampMixin):
    __tablename__ = "research_insights"
    __table_args__ = (
        Index("idx_research_insights_topic_type", "topic_id", "insight_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    insight_type: Mapped[str] = mapped_column(Text, nullable=False)  # gap/opportunity/risk/trend/contradiction
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_document_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    evidence_chunk_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    suggested_questions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    suggested_experiments: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    model_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchNote(Base, TimestampMixin):
    __tablename__ = "research_notes"
    __table_args__ = (
        Index("idx_research_notes_user_topic", "user_id", "topic_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)  # manual/chat_pin/pulse/briefing/gap
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
