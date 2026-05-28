"""Partial index for fast `WHERE favorite=true` lookup of user_document_states.

Revision ID: 0017_user_doc_favorite_index
Revises: 0016_eval_tables
Create Date: 2026-05-28 21:30:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0017_user_doc_favorite_index"
down_revision: Union[str, None] = "0016_eval_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `last_opened_at DESC NULLS LAST` so the index naturally serves the
    # "my favorites, newest-touched first" listing without an extra sort.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_uds_user_favorite
        ON user_document_states (user_id, last_opened_at DESC NULLS LAST)
        WHERE favorite = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_uds_user_favorite")
