"""claims, claim relations, document signals

Revision ID: 0004_claims_conflicts_signals
Revises: 0003_research_ext
Create Date: 2026-05-17 21:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_claims_conflicts_signals"
down_revision: Union[str, None] = "0003_research_ext"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_claims",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.BigInteger(), sa.ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("dataset", sa.Text(), nullable=True),
        sa.Column("metric", sa.Text(), nullable=True),
        sa.Column("setting", sa.Text(), nullable=True),
        sa.Column("polarity", sa.Text(), nullable=False, server_default="neutral"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="briefing"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_paper_claims_topic", "paper_claims", ["topic_id"])
    op.create_index("idx_paper_claims_doc", "paper_claims", ["document_id"])
    op.create_index("idx_paper_claims_topic_type", "paper_claims", ["topic_id", "claim_type"])
    op.create_index("idx_paper_claims_dataset_metric", "paper_claims", ["topic_id", "dataset", "metric"])

    op.create_table(
        "claim_relations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_a_id", sa.BigInteger(), sa.ForeignKey("paper_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_b_id", sa.BigInteger(), sa.ForeignKey("paper_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason_md", sa.Text(), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("reviewed_by_user", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("user_feedback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("topic_id", "claim_a_id", "claim_b_id", name="uq_claim_rel_pair"),
    )
    op.create_index("idx_claim_relations_topic_type", "claim_relations", ["topic_id", "relation_type"])
    op.create_index("idx_claim_relations_confidence", "claim_relations", ["topic_id", "confidence"])

    op.create_table(
        "document_signals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_type", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason_md", sa.Text(), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source", sa.Text(), nullable=False, server_default="local"),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("topic_id", "document_id", "signal_type", name="uq_doc_signals_topic_doc_type"),
    )
    op.create_index(
        "idx_document_signals_topic_type_score",
        "document_signals",
        ["topic_id", "signal_type", "score"],
    )


def downgrade() -> None:
    op.drop_index("idx_document_signals_topic_type_score", table_name="document_signals")
    op.drop_table("document_signals")
    op.drop_index("idx_claim_relations_confidence", table_name="claim_relations")
    op.drop_index("idx_claim_relations_topic_type", table_name="claim_relations")
    op.drop_table("claim_relations")
    op.drop_index("idx_paper_claims_dataset_metric", table_name="paper_claims")
    op.drop_index("idx_paper_claims_topic_type", table_name="paper_claims")
    op.drop_index("idx_paper_claims_doc", table_name="paper_claims")
    op.drop_index("idx_paper_claims_topic", table_name="paper_claims")
    op.drop_table("paper_claims")
