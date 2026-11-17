"""manual hostname/vendor overrides, auto device type flag, notification_log.event_type

Revision ID: f3b4c5d6e7a8
Revises: e1a2b3c4d5f6
Create Date: 2026-11-17 20:30:00

* hostname_locked / vendor_locked: the user typed the value by hand -- the
  scanner (reverse DNS, OUI lookup) and Omada sync must not overwrite it.
* device_type_auto: device_type was filled by the classifier, so it may be
  refined later; a user-entered type is never touched.
* notification_log.event_type: which event a logged MQTT/webhook/SMTP
  notification was about.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f3b4c5d6e7a8"
down_revision: Union[str, Sequence[str], None] = "e1a2b3c4d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("hostname_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("devices", sa.Column("vendor_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("devices", sa.Column("device_type_auto", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("notification_log", sa.Column("event_type", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("notification_log", "event_type")
    op.drop_column("devices", "device_type_auto")
    op.drop_column("devices", "vendor_locked")
    op.drop_column("devices", "hostname_locked")
