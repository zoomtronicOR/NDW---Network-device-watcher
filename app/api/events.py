from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.device import Device
from app.models.device_event import DeviceEvent
from app.schemas.device import DeviceEventOut
from app.schemas.event import EventListResponse

router = APIRouter(tags=["events"])


@router.get("/events", response_model=EventListResponse)
def list_events(
    db: Session = Depends(get_db),
    device_id: int | None = None,
    event_type: str | None = None,
    search: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = "timestamp",
    order: str = "desc",
) -> EventListResponse:
    stmt = select(
        DeviceEvent,
        Device.mac_address,
        Device.custom_name,
        Device.hostname,
        Device.vendor,
        Device.connection_type,
        Device.device_type,
        Device.is_trusted,
    ).outerjoin(
        Device, Device.id == DeviceEvent.device_id
    )

    if device_id is not None:
        stmt = stmt.where(DeviceEvent.device_id == device_id)
    if event_type:
        stmt = stmt.where(DeviceEvent.event_type == event_type)
    if start:
        stmt = stmt.where(DeviceEvent.timestamp >= start)
    if end:
        stmt = stmt.where(DeviceEvent.timestamp <= end)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                Device.mac_address.ilike(like),
                Device.custom_name.ilike(like),
                Device.hostname.ilike(like),
                DeviceEvent.ip_address.ilike(like),
            )
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    sort_columns = {
        "timestamp": DeviceEvent.timestamp,
        "event_type": DeviceEvent.event_type,
        "device": func.coalesce(Device.custom_name, Device.hostname, Device.mac_address),
        "ip_address": func.inet(DeviceEvent.ip_address),
        "details": DeviceEvent.details,
        "vendor": Device.vendor,
    }
    column = sort_columns.get(sort, DeviceEvent.timestamp)
    direction = column.desc() if order == "desc" else column.asc()
    stmt = (
        stmt.order_by(direction.nulls_last(), DeviceEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = db.execute(stmt).all()

    items = []
    for event, mac, custom_name, hostname, vendor, connection_type, device_type, is_trusted in rows:
        out = DeviceEventOut.model_validate(event)
        out.device_mac = mac
        out.device_name = custom_name or hostname
        out.device_vendor = vendor
        out.device_connection_type = connection_type
        out.device_type = device_type
        out.device_is_trusted = is_trusted
        items.append(out)

    return EventListResponse(items=items, total=total)
