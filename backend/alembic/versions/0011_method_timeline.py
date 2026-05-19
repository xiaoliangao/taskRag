"""method_entities + method_evolution_edges (v1.5 A-3 Method Timeline).

Revision ID: 0011_method_timeline
Revises: 0010_chat_session_summaries
Create Date: 2026-05-20 09:00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_method_timeline"
down_revision: Union[str, None] = "0010_chat_session_summaries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "method_entities",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("first_seen_document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aliases_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("topic_id", "normalized_name", name="uq_method_entities_norm"),
    )
    op.create_index("ix_method_entities_topic_seen", "method_entities", ["topic_id", "first_seen_at"])

    op.create_table(
        "method_evolution_edges",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_method_id", sa.BigInteger(), sa.ForeignKey("method_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_method_id", sa.BigInteger(), sa.ForeignKey("method_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("evidence_document_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "topic_id",
            "from_method_id",
            "to_method_id",
            "relation_type",
            name="uq_method_evolution_pair",
        ),
    )
    op.create_index("ix_method_evolution_topic", "method_evolution_edges", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_method_evolution_topic", table_name="method_evolution_edges")
    op.drop_table("method_evolution_edges")
    op.drop_index("ix_method_entities_topic_seen", table_name="method_entities")
    op.drop_table("method_entities")
