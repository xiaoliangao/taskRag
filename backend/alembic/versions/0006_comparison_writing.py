"""comparison_sessions/items + writing_projects/sources

Revision ID: 0006_comparison_writing
Revises: 0005_hypotheses_chatmode
Create Date: 2026-05-17 21:50:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_comparison_writing"
down_revision: Union[str, None] = "0005_hypotheses_chatmode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "comparison_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("result_md", sa.Text(), nullable=True),
        sa.Column("result_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "idx_comparison_sessions_user_topic",
        "comparison_sessions",
        ["user_id", "topic_id", "created_at"],
    )

    op.create_table(
        "comparison_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("comparison_session_id", sa.BigInteger(), sa.ForeignKey("comparison_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="target"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("comparison_session_id", "document_id", name="uq_comp_items_session_doc"),
    )

    op.create_table(
        "writing_projects",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("writing_type", sa.Text(), nullable=False, server_default="related_work"),
        sa.Column("user_intent", sa.Text(), nullable=True),
        sa.Column("scope_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("outline_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("draft_md", sa.Text(), nullable=True),
        sa.Column("citation_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "idx_writing_projects_user_topic",
        "writing_projects",
        ["user_id", "topic_id", "created_at"],
    )

    op.create_table(
        "writing_project_sources",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("writing_project_id", sa.BigInteger(), sa.ForeignKey("writing_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.BigInteger(), sa.ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.Text(), nullable=False, server_default="supporting"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("writing_project_id", "document_id", name="uq_writing_src_proj_doc"),
    )


def downgrade() -> None:
    op.drop_table("writing_project_sources")
    op.drop_index("idx_writing_projects_user_topic", table_name="writing_projects")
    op.drop_table("writing_projects")
    op.drop_table("comparison_items")
    op.drop_index("idx_comparison_sessions_user_topic", table_name="comparison_sessions")
    op.drop_table("comparison_sessions")
