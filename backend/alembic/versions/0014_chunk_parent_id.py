"""Parent-Child chunking: chunks.parent_id + is_parent + nullable vector_id.

Revision ID: 0014_chunk_parent_id
Revises: 0013_annotations
Create Date: 2026-05-21 09:00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_chunk_parent_id"
down_revision: Union[str, None] = "0013_annotations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Parent ↔ child self-reference. Parents have parent_id IS NULL and
    # is_parent=true; children carry their parent's chunk row id.
    op.add_column(
        "chunks",
        sa.Column(
            "parent_id",
            sa.BigInteger(),
            sa.ForeignKey("chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "is_parent", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    # Parent rows don't need a vector (we only embed children), so vector_id
    # becomes nullable. The unique constraint stays — Postgres allows multiple
    # NULLs in a unique index.
    op.alter_column("chunks", "vector_id", nullable=True)
    op.create_index(
        "idx_chunks_parent_id",
        "chunks",
        ["parent_id"],
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_chunks_parent_id", table_name="chunks")
    op.alter_column("chunks", "vector_id", nullable=False)
    op.drop_column("chunks", "is_parent")
    op.drop_column("chunks", "parent_id")
