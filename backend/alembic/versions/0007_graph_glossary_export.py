"""document_relations + topic_glossary_terms + export_jobs

Revision ID: 0007_graph_glossary_export
Revises: 0006_comparison_writing
Create Date: 2026-05-17 22:10:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_graph_glossary_export"
down_revision: Union[str, None] = "0006_comparison_writing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_relations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source", sa.Text(), nullable=False, server_default="local"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("topic_id", "source_document_id", "target_document_id", "relation_type", name="uq_doc_rel_uniq"),
    )
    op.create_index("idx_doc_rel_topic", "document_relations", ["topic_id"])
    op.create_index("idx_doc_rel_type", "document_relations", ["topic_id", "relation_type"])

    op.create_table(
        "topic_glossary_terms",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term_id", sa.BigInteger(), sa.ForeignKey("topic_terms.id", ondelete="SET NULL"), nullable=True),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("normalized_term", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("aliases_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("representative_document_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source", sa.Text(), nullable=False, server_default="auto"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("topic_id", "normalized_term", name="uq_glossary_topic_norm"),
    )
    op.create_index("idx_glossary_topic", "topic_glossary_terms", ["topic_id"])

    op.create_table(
        "export_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("export_type", sa.Text(), nullable=False),
        sa.Column("scope_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_export_jobs_user_topic", "export_jobs", ["user_id", "topic_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_export_jobs_user_topic", table_name="export_jobs")
    op.drop_table("export_jobs")
    op.drop_index("idx_glossary_topic", table_name="topic_glossary_terms")
    op.drop_table("topic_glossary_terms")
    op.drop_index("idx_doc_rel_type", table_name="document_relations")
    op.drop_index("idx_doc_rel_topic", table_name="document_relations")
    op.drop_table("document_relations")
