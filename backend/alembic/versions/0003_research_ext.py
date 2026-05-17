"""research extensions: terms + trend snapshots

Revision ID: 0003_research_ext
Revises: 0002_intelligence_layer
Create Date: 2026-05-17 20:30:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_research_ext"
down_revision: Union[str, None] = "0002_intelligence_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # topic_terms
    op.create_table(
        "topic_terms",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("normalized_term", sa.Text(), nullable=False),
        sa.Column("term_type", sa.Text(), nullable=False, server_default="keyword"),
        sa.Column("source", sa.Text(), nullable=False, server_default="auto"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trend_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("topic_id", "normalized_term", name="uq_topic_terms_norm"),
    )
    op.create_index("idx_topic_terms_topic", "topic_terms", ["topic_id"])
    op.create_index("idx_topic_terms_topic_type", "topic_terms", ["topic_id", "term_type"])
    op.create_index("idx_topic_terms_topic_score", "topic_terms", ["topic_id", "trend_score"])

    # term_occurrences
    op.create_table(
        "term_occurrences",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term_id", sa.BigInteger(), sa.ForeignKey("topic_terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.BigInteger(), sa.ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_field", sa.Text(), nullable=False),
        sa.Column("context_text", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "topic_id", "term_id", "document_id", "source_field",
            name="uq_term_occ_topic_term_doc_field",
        ),
    )
    op.create_index("idx_term_occ_topic_doc", "term_occurrences", ["topic_id", "document_id"])
    op.create_index("idx_term_occ_term_time", "term_occurrences", ["term_id", "occurred_at"])

    # topic_trend_runs
    op.create_table(
        "topic_trend_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("bucket", sa.Text(), nullable=False, server_default="week"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("summary_md", sa.Text(), nullable=True),
        sa.Column("heatmap_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_trend_runs_topic_time", "topic_trend_runs", ["topic_id", "generated_at"])

    # topic_trend_items
    op.create_table(
        "topic_trend_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trend_run_id", sa.BigInteger(), sa.ForeignKey("topic_trend_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term_id", sa.BigInteger(), sa.ForeignKey("topic_terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("term_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("frequency_recent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("frequency_baseline", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("growth_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_document_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_trend_items_run", "topic_trend_items", ["trend_run_id"])
    op.create_index("idx_trend_items_topic_status", "topic_trend_items", ["topic_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_trend_items_topic_status", table_name="topic_trend_items")
    op.drop_index("idx_trend_items_run", table_name="topic_trend_items")
    op.drop_table("topic_trend_items")

    op.drop_index("idx_trend_runs_topic_time", table_name="topic_trend_runs")
    op.drop_table("topic_trend_runs")

    op.drop_index("idx_term_occ_term_time", table_name="term_occurrences")
    op.drop_index("idx_term_occ_topic_doc", table_name="term_occurrences")
    op.drop_table("term_occurrences")

    op.drop_index("idx_topic_terms_topic_score", table_name="topic_terms")
    op.drop_index("idx_topic_terms_topic_type", table_name="topic_terms")
    op.drop_index("idx_topic_terms_topic", table_name="topic_terms")
    op.drop_table("topic_terms")
