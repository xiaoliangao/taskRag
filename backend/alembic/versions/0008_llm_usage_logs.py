"""llm_usage_logs (v1.4 observability)

Revision ID: 0008_llm_usage_logs
Revises: 0007_graph_glossary_export
Create Date: 2026-05-19 09:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_llm_usage_logs"
down_revision: Union[str, None] = "0007_graph_glossary_export"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feature", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_llm_usage_logs_user_created",
        "llm_usage_logs",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_llm_usage_logs_feature_created",
        "llm_usage_logs",
        ["feature", "created_at"],
    )
    op.create_index(
        "ix_llm_usage_logs_topic_created",
        "llm_usage_logs",
        ["topic_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_usage_logs_topic_created", table_name="llm_usage_logs")
    op.drop_index("ix_llm_usage_logs_feature_created", table_name="llm_usage_logs")
    op.drop_index("ix_llm_usage_logs_user_created", table_name="llm_usage_logs")
    op.drop_table("llm_usage_logs")
