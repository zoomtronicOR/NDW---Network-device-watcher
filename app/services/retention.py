from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.device_event import DeviceEvent
from app.models.ip_history import IpHistory
from app.models.notification_log import NotificationLog


def cleanup_history(db: Session, retention_days: int | None) -> dict[str, int]:
    """Delete device_events/ip_history/notification_log rows older than the
    configured retention window (§19.1). Per-device latest
    state (the devices table itself -- first_seen, last_seen, appearance
    count, ...) is never touched, only the detailed history behind it.

    retention_days=None means "unlimited" -- a no-op.
    """
    if not retention_days:
        return {"device_events": 0, "ip_history": 0, "notification_log": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    events_deleted = db.execute(delete(DeviceEvent).where(DeviceEvent.timestamp < cutoff)).rowcount
    ip_history_deleted = db.execute(delete(IpHistory).where(IpHistory.last_seen < cutoff)).rowcount
    notifications_deleted = db.execute(delete(NotificationLog).where(NotificationLog.timestamp < cutoff)).rowcount
    db.commit()

    return {
        "device_events": events_deleted,
        "ip_history": ip_history_deleted,
        "notification_log": notifications_deleted,
    }


def cleanup_ping_results(db: Session, retention_days: int | None) -> int:
    """Ping statistics have their own retention (Settings -> Istorija), since
    at a few-second ping interval they grow far faster than device history.
    retention_days=None means unlimited."""
    from app.models.ping_result import PingResult

    if not retention_days:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = 0
    # Batched so a first run against millions of rows doesn't hold one huge
    # transaction/lock while the pinger keeps inserting.
    while True:
        ids = select(PingResult.id).where(PingResult.timestamp < cutoff).limit(20000).scalar_subquery()
        n = db.execute(delete(PingResult).where(PingResult.id.in_(ids))).rowcount
        db.commit()
        deleted += n
        if n < 20000:
            return deleted
