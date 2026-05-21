"""RAGAS-style eval tables: rag_eval_questions + rag_eval_runs (Wave-3 Pkg-Eval).

Revision ID: 0016_eval_tables
Revises: 0015_chunk_context_summary
Create Date: 2026-05-21 11:00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_eval_tables"
down_revision: Union[str, None] = "0015_chunk_context_summary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_eval_questions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "topic_id",
            sa.BigInteger(),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=True),
        # IDs of chunks (children, not parents) that an ideal retrieval should
        # return for this question. Stored as JSONB so we can also annotate
        # weights / why-it-matters notes later without a migration.
        sa.Column(
            "expected_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # Optional tag e.g. "factual" / "comparison" — used to slice metrics
        # by query type and compare against the router's classifications.
        sa.Column("tag", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_rag_eval_questions_topic", "rag_eval_questions", ["topic_id"]
    )

    op.create_table(
        "rag_eval_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "topic_id",
            sa.BigInteger(),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Short identifier so the user can group runs ("baseline", "after-cr",
        # "after-qr"). Free-text — humans pick.
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("commit_sha", sa.Text(), nullable=True),
        # Aggregate metrics: {"recall_at_5": 0.61, "recall_at_20": 0.84,
        # "mrr": 0.47, "n_questions": 30, "per_route": {...}}
        sa.Column(
            "metrics_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_rag_eval_runs_topic_created",
        "rag_eval_runs",
        ["topic_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_rag_eval_runs_topic_created", table_name="rag_eval_runs")
    op.drop_table("rag_eval_runs")
    op.drop_index("idx_rag_eval_questions_topic", table_name="rag_eval_questions")
    op.drop_table("rag_eval_questions")
