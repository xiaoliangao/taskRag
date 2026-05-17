"""hypothesis checks/evidence + chat_sessions.mode

Revision ID: 0005_hypotheses_chatmode
Revises: 0004_claims_conflicts_signals
Create Date: 2026-05-17 21:30:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_hypotheses_chatmode"
down_revision: Union[str, None] = "0004_claims_conflicts_signals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hypothesis_checks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("result_md", sa.Text(), nullable=True),
        sa.Column("result_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_hypothesis_checks_topic", "hypothesis_checks", ["topic_id", "created_at"])

    op.create_table(
        "hypothesis_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("check_id", sa.BigInteger(), sa.ForeignKey("hypothesis_checks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.BigInteger(), sa.ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stance", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_hypothesis_evidence_check", "hypothesis_evidence", ["check_id"])

    op.add_column(
        "chat_sessions",
        sa.Column("mode", sa.Text(), nullable=False, server_default="default"),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "mode")
    op.drop_index("idx_hypothesis_evidence_check", table_name="hypothesis_evidence")
    op.drop_table("hypothesis_evidence")
    op.drop_index("idx_hypothesis_checks_topic", table_name="hypothesis_checks")
    op.drop_table("hypothesis_checks")
