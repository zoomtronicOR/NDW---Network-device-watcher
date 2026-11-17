"""ping_results (target_id, timestamp) composite index

Revision ID: e1a2b3c4d5f6
Revises: d66e87304256
Create Date: 2026-11-17 19:30:00

Range queries on the Ping tab (1h..10d per target, bucketed) filter on both
columns; with separate single-column indexes Postgres had to intersect them.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e1a2b3c4d5f6"
down_revision: Union[str, Sequence[str], None] = "d66e87304256"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_ping_results_target_ts", "ping_results", ["target_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_ping_results_target_ts", table_name="ping_results")
