from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.device import Device
from app.models.device_event import DeviceEvent
from app.models.ip_history import IpHistory
from app.schemas.timemachine import TimeMachineBounds, TimeMachineDeviceOut, TimeMachineResponse

router = APIRouter(prefix="/timemachine", tags=["timemachine"])

# Only these event types affect ONLINE/OFFLINE status (§7);
# the most recent one at-or-before the target time tells us the status then.
_STATUS_EVENTS = ("NEW_DEVICE", "DEVICE_RETURNED", "DEVICE_OFFLINE")


def _reconstruct(db: Session, at: datetime) -> list[TimeMachineDeviceOut]:
    devices = db.execute(select(Device).where(Device.first_seen <= at)).scalars().all()

    results: list[TimeMachineDeviceOut] = []
    for device in devices:
        event = db.execute(
            select(DeviceEvent)
            .where(
                DeviceEvent.device_id == device.id,
                DeviceEvent.event_type.in_(_STATUS_EVENTS),
                DeviceEvent.timestamp <= at,
            )
            .order_by(DeviceEvent.timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()
        if event is None:
            continue  # first_seen <= at but no status event yet -- shouldn't happen, skip defensively

        online = event.event_type != "DEVICE_OFFLINE"

        ip_row = db.execute(
            select(IpHistory)
            .where(IpHistory.device_id == device.id, IpHistory.first_seen <= at)
            .order_by(IpHistory.first_seen.desc())
            .limit(1)
        ).scalar_one_or_none()

        results.append(
            TimeMachineDeviceOut(
                device_id=device.id,
                mac_address=device.mac_address,
                ip_address=ip_row.ip_address if ip_row else None,
                hostname=device.hostname,
                vendor=device.vendor,
                custom_name=device.custom_name,
                online=online,
                status_changed_at=event.timestamp,
                first_seen=device.first_seen,
            )
        )
    return results


@router.get("/state", response_model=TimeMachineResponse)
def get_state(at: datetime, db: Session = Depends(get_db)) -> TimeMachineResponse:
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)

    snapshot = _reconstruct(db, at)
    online_at_t = {d.mac_address for d in snapshot if d.online}

    current_online = {
        d.mac_address for d in db.execute(select(Device).where(Device.is_online.is_(True))).scalars().all()
    }

    return TimeMachineResponse(
        at=at,
        devices=sorted(snapshot, key=lambda d: d.mac_address),
        online_count=len(online_at_t),
        offline_count=len(snapshot) - len(online_at_t),
        appeared_since=sorted(current_online - online_at_t),
        disappeared_since=sorted(online_at_t - current_online),
    )


@router.get("/bounds", response_model=TimeMachineBounds)
def get_bounds(db: Session = Depends(get_db)) -> TimeMachineBounds:
    earliest = db.execute(select(func.min(Device.first_seen))).scalar_one_or_none()
    return TimeMachineBounds(earliest=earliest, latest=datetime.now(timezone.utc))
