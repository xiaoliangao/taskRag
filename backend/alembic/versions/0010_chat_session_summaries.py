"""chat_session_summaries (v1.4 Sprint 7 Conversation Memory).

Revision ID: 0010_chat_session_summaries
Revises: 0009_chunks_fts
Create Date: 2026-05-19 11:00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_chat_session_summaries"
down_revision: Union[str, None] = "0009_chunks_fts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_session_summaries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_session_id", sa.BigInteger(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary_md", sa.Text(), nullable=False),
        sa.Column("memory_items_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("message_count_at_gen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("chat_session_id", name="uq_chat_session_summaries_session"),
    )
    op.create_index(
        "ix_chat_session_summaries_user_topic",
        "chat_session_summaries",
        ["user_id", "topic_id", "generated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_session_summaries_user_topic", table_name="chat_session_summaries")
    op.drop_table("chat_session_summaries")
