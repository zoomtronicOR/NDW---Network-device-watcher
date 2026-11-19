"""ping_targets.sort_order -- user-defined order of ping destinations

Revision ID: a7c8d9e0f1b2
Revises: f3b4c5d6e7a8
Create Date: 2026-11-19 19:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7c8d9e0f1b2"
down_revision: Union[str, Sequence[str], None] = "f3b4c5d6e7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ping_targets", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    # Keep the existing (creation) order.
    op.execute(
        "UPDATE ping_targets t SET sort_order = s.rn FROM "
        "(SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM ping_targets) s WHERE s.id = t.id"
    )


def downgrade() -> None:
    op.drop_column("ping_targets", "sort_order")
