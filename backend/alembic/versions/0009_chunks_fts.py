"""chunks: add tsvector + GIN index for BM25 hybrid search (v1.4 Sprint 6).

Revision ID: 0009_chunks_fts
Revises: 0008_llm_usage_logs
Create Date: 2026-05-19 10:00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_chunks_fts"
down_revision: Union[str, None] = "0008_llm_usage_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Generated column: tsvector('english', text). Stored so the GIN index can be used efficiently.
    op.execute(
        sa.text(
            "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED"
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_chunks_text_tsv ON chunks USING GIN (text_tsv)")
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chunks_text_tsv"))
    op.execute(sa.text("ALTER TABLE chunks DROP COLUMN IF EXISTS text_tsv"))
