"""Record every external notification attempt (§29,
`notification_log`): SMTP, MQTT event topics and webhooks, including the
ones deliberately skipped (quiet hours / trusted device) so it's visible
*why* nothing arrived. Never raises -- logging must not block detection."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from sqlalchemy import select

from app.database import SessionLocal
from app.models.device import Device
from app.models.notification_log import NotificationLog

logger = logging.getLogger("networkwatcher.notification_log")

SUCCESS = "SUCCESS"
FAILED = "FAILED"
SKIPPED = "SKIPPED"


def safe_url(url: str) -> str:
    """Drop query string / credentials -- tokens often live there."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return f"{parts.scheme}://{host}{parts.path}"[:255]
    except Exception:
        return url[:255]


def record(
    channel: str,
    event_type: str | None,
    mac: str | None,
    destination: str,
    status: str,
    error: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        device_id = None
        if mac:
            device_id = db.execute(select(Device.id).where(Device.mac_address == mac)).scalar_one_or_none()
        db.add(
            NotificationLog(
                device_id=device_id,
                notification_type=channel,
                event_type=event_type,
                destination=(destination or "-")[:255],
                status=status,
                error=error,
            )
        )
        db.commit()
    except Exception:
        logger.exception("could not write notification_log")
        db.rollback()
    finally:
        db.close()
