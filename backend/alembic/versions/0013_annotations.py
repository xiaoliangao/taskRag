"""annotations table for in-app PDF highlights/comments/notes.

Revision ID: 0013_annotations
Revises: 0012_user_admin_flags
Create Date: 2026-05-19 22:00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_annotations"
down_revision: Union[str, None] = "0012_user_admin_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "annotations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.BigInteger(),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.BigInteger(),
            sa.ForeignKey("chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),  # 'highlight' | 'comment' | 'note'
        sa.Column(
            "color", sa.Text(), nullable=False, server_default=sa.text("'#fff59d'")
        ),
        sa.Column("selected_text", sa.Text(), nullable=False),
        sa.Column(
            "rects",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("comment_md", sa.Text(), nullable=True),
        sa.Column(
            "note_id",
            sa.BigInteger(),
            sa.ForeignKey("research_notes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_annotations_doc_page", "annotations", ["document_id", "page_number"]
    )
    op.create_index(
        "idx_annotations_user_topic", "annotations", ["user_id", "topic_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_annotations_user_topic", table_name="annotations")
    op.drop_index("idx_annotations_doc_page", table_name="annotations")
    op.drop_table("annotations")
