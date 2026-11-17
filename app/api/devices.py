from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.device import Device
from app.models.device_event import DeviceEvent
from app.models.enums import EventType
from app.models.ip_history import IpHistory
from app.schemas.device import DeviceDetailOut, DeviceListResponse, DeviceOut, DeviceUpdate
from app.services.vendor import lookup_vendor

router = APIRouter(tags=["devices"])

_SORT_FIELDS = {
    "last_seen": Device.last_seen,
    "first_seen": Device.first_seen,
    "ip_address": Device.ip_address,
    "mac_address": Device.mac_address,
    "hostname": Device.hostname,
    "vendor": Device.vendor,
    "seen_count": Device.seen_count,
    "connection_type": Device.connection_type,
    "wifi_rssi": Device.wifi_rssi,
    "custom_name": Device.custom_name,
    "notes": Device.notes,
    "device_type": Device.device_type,
    "wifi_ssid": Device.wifi_ssid,
    "interface": Device.interface,
}


@router.get("/devices", response_model=DeviceListResponse)
def list_devices(
    db: Session = Depends(get_db),
    search: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    connection_type: str | None = None,
    is_trusted: bool | None = None,
    sort: str = "last_seen",
    order: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> DeviceListResponse:
    stmt = select(Device)

    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                Device.mac_address.ilike(like),
                Device.ip_address.ilike(like),
                Device.hostname.ilike(like),
                Device.vendor.ilike(like),
                Device.custom_name.ilike(like),
                Device.dhcp_hostname.ilike(like),
                Device.device_type.ilike(like),
            )
        )
    if connection_type:
        stmt = stmt.where(Device.connection_type == connection_type)
    if is_trusted is not None:
        stmt = stmt.where(Device.is_trusted == is_trusted)
    if status_filter == "NEW":
        stmt = stmt.where(Device.is_new.is_(True))
    elif status_filter == "ONLINE":
        stmt = stmt.where(Device.is_online.is_(True), Device.is_new.is_(False))
    elif status_filter == "OFFLINE":
        # Status badges are mutually exclusive (compute_status: NEW wins), so
        # each filter must match exactly its own badge -- this used to also
        # return not-yet-acknowledged NEW devices that happened to be offline.
        stmt = stmt.where(Device.is_online.is_(False), Device.is_new.is_(False))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    desc = order == "desc"
    if sort == "status":
        # Same precedence as compute_status(): NEW, then ONLINE, then OFFLINE.
        rank = case((Device.is_new.is_(True), 0), (Device.is_online.is_(True), 1), else_=2)
        order_by = [rank.desc() if desc else rank.asc()]
    else:
        column = _SORT_FIELDS.get(sort, Device.last_seen)
        if column is Device.ip_address:
            # Numeric IP order (192.168.1.9 before 192.168.1.10), not text order.
            column = func.inet(Device.ip_address)
        order_by = [(column.desc() if desc else column.asc()).nulls_last()]
    stmt = stmt.order_by(*order_by, Device.id.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    devices = db.execute(stmt).scalars().all()
    return DeviceListResponse(items=[DeviceOut.from_device(d) for d in devices], total=total)


@router.get("/devices/{device_id}", response_model=DeviceDetailOut)
def get_device(device_id: int, db: Session = Depends(get_db)) -> DeviceDetailOut:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    if device.is_new:
        device.is_new = False
        db.commit()
        db.refresh(device)

    ip_history = (
        db.execute(select(IpHistory).where(IpHistory.device_id == device_id).order_by(IpHistory.last_seen.desc()))
        .scalars()
        .all()
    )
    events = (
        db.execute(
            select(DeviceEvent).where(DeviceEvent.device_id == device_id).order_by(DeviceEvent.timestamp.desc()).limit(100)
        )
        .scalars()
        .all()
    )

    return DeviceDetailOut.from_device_detail(device, ip_history=ip_history, events=events)


@router.patch("/devices/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, payload: DeviceUpdate, db: Session = Depends(get_db)) -> DeviceOut:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    requested = payload.model_dump(exclude_unset=True)
    changes: dict = {}
    for field_name, value in requested.items():
        if isinstance(value, str):
            value = value.strip() or None
        current = getattr(device, field_name)

        if field_name in ("hostname", "vendor"):
            lock_attr = f"{field_name}_locked"
            if value is None:
                # Cleared -> back to automatic detection. Restore the automatic
                # value right away (Omada only replaces an empty or
                # Omada-sourced hostname, so a stale manual one would stick).
                if getattr(device, lock_attr):
                    setattr(device, lock_attr, False)
                    if field_name == "hostname":
                        device.hostname = device.dhcp_hostname
                    else:
                        device.vendor = lookup_vendor(device.mac_address)
                    changes[field_name] = "(automatski)"
                continue
            if value != current:
                setattr(device, field_name, value)
                setattr(device, lock_attr, True)
                changes[field_name] = value
            continue

        if field_name == "device_type":
            if value != current:
                device.device_type = value
                # A typed value is the user's; clearing hands it back to the classifier.
                device.device_type_auto = False
                changes[field_name] = value
            continue

        if value != current:
            setattr(device, field_name, value)
            changes[field_name] = value

    if changes:
        db.add(
            DeviceEvent(
                device_id=device.id,
                event_type=EventType.MANUAL_UPDATE.value,
                ip_address=device.ip_address,
                timestamp=datetime.now(timezone.utc),
                details=json.dumps(changes),
            )
        )
        db.commit()
        db.refresh(device)

    return DeviceOut.from_device(device)


@router.delete("/devices/{device_id}", status_code=204)
def delete_device(device_id: int, db: Session = Depends(get_db)) -> None:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(device)
    db.commit()
