"""intelligence layer: briefings, insights, user states, pulses, paths, notes

Revision ID: 0002_intelligence_layer
Revises: 0001_initial
Create Date: 2026-05-16 10:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_intelligence_layer"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # document_briefings
    op.create_table(
        "document_briefings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("language", sa.Text(), nullable=False, server_default="zh-CN"),
        sa.Column("one_sentence_summary", sa.Text(), nullable=True),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("contributions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("experiments", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("limitations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("datasets", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("code_available", sa.Boolean(), nullable=True),
        sa.Column("code_url", sa.Text(), nullable=True),
        sa.Column("reading_time_minutes", sa.Integer(), nullable=True),
        sa.Column("evidence_chunk_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("model_provider", sa.Text(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "language", name="uq_doc_briefing_doc_lang"),
    )
    op.create_index("ix_document_briefings_document_id", "document_briefings", ["document_id"])

    # topic_document_insights
    op.create_table(
        "topic_document_insights",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("relevance_reason", sa.Text(), nullable=True),
        sa.Column("reading_priority", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("why_read", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("topic_id", "document_id", name="uq_topic_doc_insight"),
    )
    op.create_index("ix_topic_document_insights_topic_id", "topic_document_insights", ["topic_id"])
    op.create_index("ix_topic_document_insights_document_id", "topic_document_insights", ["document_id"])

    # user_document_states
    op.create_table(
        "user_document_states",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="unread"),
        sa.Column("favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("personal_note", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "document_id", name="uq_user_doc_state"),
    )
    op.create_index("ix_user_document_states_user_id", "user_document_states", ["user_id"])
    op.create_index("ix_user_document_states_document_id", "user_document_states", ["document_id"])

    # topic_pulses
    op.create_table(
        "topic_pulses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pulse_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("summary_md", sa.Text(), nullable=True),
        sa.Column("highlights", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("new_documents", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("important_documents", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("emerging_keywords", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("suggested_actions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("citations_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("model_provider", sa.Text(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("topic_id", "pulse_date", name="uq_topic_pulse_date"),
    )
    op.create_index("ix_topic_pulses_topic_id", "topic_pulses", ["topic_id"])

    # reading_paths
    op.create_table(
        "reading_paths",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("scope", sa.Text(), nullable=False, server_default="topic"),
        sa.Column("config_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reading_paths_topic_id", "reading_paths", ["topic_id"])

    # reading_path_items
    op.create_table(
        "reading_path_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("reading_path_id", sa.BigInteger(), sa.ForeignKey("reading_paths.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expected_minutes", sa.Integer(), nullable=True),
        sa.Column("prerequisite_document_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reading_path_id", "document_id", name="uq_rp_item_doc"),
    )
    op.create_index("idx_rp_item_order", "reading_path_items", ["reading_path_id", "order_index"])

    # research_insights
    op.create_table(
        "research_insights",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("insight_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("detail_md", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_document_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("evidence_chunk_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("suggested_questions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("suggested_experiments", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("model_provider", sa.Text(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_research_insights_topic_type", "research_insights", ["topic_id", "insight_type"])

    # research_notes
    op.create_table(
        "research_notes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_research_notes_user_topic", "research_notes", ["user_id", "topic_id", "created_at"])


def downgrade() -> None:
    op.drop_table("research_notes")
    op.drop_table("research_insights")
    op.drop_table("reading_path_items")
    op.drop_table("reading_paths")
    op.drop_table("topic_pulses")
    op.drop_table("user_document_states")
    op.drop_table("topic_document_insights")
    op.drop_table("document_briefings")
