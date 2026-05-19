"""users.is_admin + users.disabled_at for admin panel.

Revision ID: 0012_user_admin_flags
Revises: 0011_method_timeline
Create Date: 2026-05-19 21:00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_user_admin_flags"
down_revision: Union[str, None] = "0011_method_timeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_is_admin", "users", ["is_admin"], postgresql_where=sa.text("is_admin"))


def downgrade() -> None:
    op.drop_index("idx_users_is_admin", table_name="users")
    op.drop_column("users", "disabled_at")
    op.drop_column("users", "is_admin")
