from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.device import Device
from app.models.notification_log import NotificationLog

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def list_notifications(
    db: Session = Depends(get_db),
    channel: str | None = None,
    status: str | None = None,
    event_type: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = "timestamp",
    order: str = "desc",
) -> dict:
    """notification_log (§29) for Sistem -> Obaveštenja: every SMTP /
    MQTT / webhook notification, including skipped ones and the reason."""
    stmt = select(NotificationLog, Device.mac_address, Device.custom_name, Device.hostname).outerjoin(
        Device, Device.id == NotificationLog.device_id
    )
    if channel:
        stmt = stmt.where(NotificationLog.notification_type == channel)
    if status:
        stmt = stmt.where(NotificationLog.status == status)
    if event_type:
        stmt = stmt.where(NotificationLog.event_type == event_type)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                Device.mac_address.ilike(like),
                Device.custom_name.ilike(like),
                Device.hostname.ilike(like),
                NotificationLog.destination.ilike(like),
                NotificationLog.error.ilike(like),
            )
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    columns = {
        "timestamp": NotificationLog.timestamp,
        "channel": NotificationLog.notification_type,
        "event_type": NotificationLog.event_type,
        "device": func.coalesce(Device.custom_name, Device.hostname, Device.mac_address),
        "destination": NotificationLog.destination,
        "status": NotificationLog.status,
        "error": NotificationLog.error,
    }
    column = columns.get(sort, NotificationLog.timestamp)
    direction = column.desc() if order == "desc" else column.asc()
    rows = db.execute(
        stmt.order_by(direction.nulls_last(), NotificationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    summary = dict(
        db.execute(select(NotificationLog.status, func.count()).group_by(NotificationLog.status)).all()
    )
    return {
        "total": total,
        "summary": summary,
        "items": [
            {
                "id": n.id,
                "timestamp": n.timestamp.isoformat(),
                "channel": n.notification_type,
                "event_type": n.event_type,
                "device_id": n.device_id,
                "device_mac": mac,
                "device_name": custom_name or hostname,
                "destination": n.destination,
                "status": n.status,
                "error": n.error,
            }
            for n, mac, custom_name, hostname in rows
        ],
    }
