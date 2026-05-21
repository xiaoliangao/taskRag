"""Contextual Retrieval: chunks.context_summary for LLM-generated situating context.

Revision ID: 0015_chunk_context_summary
Revises: 0014_chunk_parent_id
Create Date: 2026-05-21 10:00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_chunk_context_summary"
down_revision: Union[str, None] = "0014_chunk_parent_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("context_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chunks", "context_summary")
