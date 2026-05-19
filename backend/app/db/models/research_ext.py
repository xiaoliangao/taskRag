"""Models for v1.3+ research extensions (Trend Radar etc.)."""
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


class TopicTerm(Base, TimestampMixin):
    __tablename__ = "topic_terms"
    __table_args__ = (
        UniqueConstraint("topic_id", "normalized_term", name="uq_topic_terms_norm"),
        Index("idx_topic_terms_topic", "topic_id"),
        Index("idx_topic_terms_topic_type", "topic_id", "term_type"),
        Index("idx_topic_terms_topic_score", "topic_id", "trend_score"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    term: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_term: Mapped[str] = mapped_column(Text, nullable=False)
    term_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="keyword")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="auto")
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    trend_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )


class TermOccurrence(Base):
    __tablename__ = "term_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "topic_id", "term_id", "document_id", "source_field",
            name="uq_term_occ_topic_term_doc_field",
        ),
        Index("idx_term_occ_topic_doc", "topic_id", "document_id"),
        Index("idx_term_occ_term_time", "term_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topic_terms.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    source_field: Mapped[str] = mapped_column(Text, nullable=False)
    context_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TopicTrendRun(Base):
    __tablename__ = "topic_trend_runs"
    __table_args__ = (
        Index("idx_trend_runs_topic_time", "topic_id", "generated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    bucket: Mapped[str] = mapped_column(Text, nullable=False, server_default="week")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    summary_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    heatmap_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PaperClaim(Base, TimestampMixin):
    __tablename__ = "paper_claims"
    __table_args__ = (
        Index("idx_paper_claims_topic", "topic_id"),
        Index("idx_paper_claims_doc", "document_id"),
        Index("idx_paper_claims_topic_type", "topic_id", "claim_type"),
        Index("idx_paper_claims_dataset_metric", "topic_id", "dataset", "metric"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric: Mapped[str | None] = mapped_column(Text, nullable=True)
    setting: Mapped[str | None] = mapped_column(Text, nullable=True)
    polarity: Mapped[str] = mapped_column(Text, nullable=False, server_default="neutral")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="briefing")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )


class ClaimRelation(Base, TimestampMixin):
    __tablename__ = "claim_relations"
    __table_args__ = (
        UniqueConstraint(
            "topic_id", "claim_a_id", "claim_b_id",
            name="uq_claim_rel_pair",
        ),
        Index("idx_claim_relations_topic_type", "topic_id", "relation_type"),
        Index("idx_claim_relations_confidence", "topic_id", "confidence"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    claim_a_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paper_claims.id", ondelete="CASCADE"), nullable=False
    )
    claim_b_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paper_claims.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    reason_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    reviewed_by_user: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentRelation(Base):
    __tablename__ = "document_relations"
    __table_args__ = (
        UniqueConstraint(
            "topic_id", "source_document_id", "target_document_id", "relation_type",
            name="uq_doc_rel_uniq",
        ),
        Index("idx_doc_rel_topic", "topic_id"),
        Index("idx_doc_rel_type", "topic_id", "relation_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    source_document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    target_document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="local")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TopicGlossaryTerm(Base, TimestampMixin):
    __tablename__ = "topic_glossary_terms"
    __table_args__ = (
        UniqueConstraint(
            "topic_id", "normalized_term", name="uq_glossary_topic_norm"
        ),
        Index("idx_glossary_topic", "topic_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("topic_terms.id", ondelete="SET NULL"), nullable=True
    )
    term: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_term: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    representative_document_ids: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="auto")


class ExportJob(Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        Index("idx_export_jobs_user_topic", "user_id", "topic_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    export_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ComparisonSession(Base, TimestampMixin):
    __tablename__ = "comparison_sessions"
    __table_args__ = (
        Index("idx_comparison_sessions_user_topic", "user_id", "topic_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    result_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ComparisonItem(Base):
    __tablename__ = "comparison_items"
    __table_args__ = (
        UniqueConstraint(
            "comparison_session_id", "document_id", name="uq_comp_items_session_doc"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    comparison_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("comparison_sessions.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="target")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WritingProject(Base, TimestampMixin):
    __tablename__ = "writing_projects"
    __table_args__ = (
        Index("idx_writing_projects_user_topic", "user_id", "topic_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    writing_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="related_work")
    user_intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    outline_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    draft_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class WritingProjectSource(Base):
    __tablename__ = "writing_project_sources"
    __table_args__ = (
        UniqueConstraint(
            "writing_project_id", "document_id", name="uq_writing_src_proj_doc"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    writing_project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("writing_projects.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="supporting")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class HypothesisCheck(Base, TimestampMixin):
    __tablename__ = "hypothesis_checks"
    __table_args__ = (
        Index("idx_hypothesis_checks_topic", "topic_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HypothesisEvidence(Base):
    __tablename__ = "hypothesis_evidence"
    __table_args__ = (
        Index("idx_hypothesis_evidence_check", "check_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    check_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hypothesis_checks.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    stance: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentSignal(Base):
    __tablename__ = "document_signals"
    __table_args__ = (
        UniqueConstraint(
            "topic_id", "document_id", "signal_type",
            name="uq_doc_signals_topic_doc_type",
        ),
        Index(
            "idx_document_signals_topic_type_score",
            "topic_id", "signal_type", "score",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    signal_type: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    reason_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="local")
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TopicTrendItem(Base):
    __tablename__ = "topic_trend_items"
    __table_args__ = (
        Index("idx_trend_items_run", "trend_run_id"),
        Index("idx_trend_items_topic_status", "topic_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trend_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topic_trend_runs.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topic_terms.id", ondelete="CASCADE"), nullable=False
    )
    term: Mapped[str] = mapped_column(Text, nullable=False)
    term_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    frequency_recent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    frequency_baseline: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    growth_rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    evidence_document_ids: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---- v1.5 A-3: Method Timeline ----


class MethodEntity(Base, TimestampMixin):
    __tablename__ = "method_entities"
    __table_args__ = (
        UniqueConstraint("topic_id", "normalized_name", name="uq_method_entities_norm"),
        Index("ix_method_entities_topic_seen", "topic_id", "first_seen_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    aliases_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )


class MethodEvolutionEdge(Base):
    __tablename__ = "method_evolution_edges"
    __table_args__ = (
        UniqueConstraint(
            "topic_id", "from_method_id", "to_method_id", "relation_type",
            name="uq_method_evolution_pair",
        ),
        Index("ix_method_evolution_topic", "topic_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    from_method_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("method_entities.id", ondelete="CASCADE"), nullable=False
    )
    to_method_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("method_entities.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_document_ids: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
