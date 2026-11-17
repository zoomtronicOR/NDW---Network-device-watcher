from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.device import Device
from app.models.device_event import DeviceEvent
from app.models.enums import EventType
from app.services.notification_gate import local_timezone

router = APIRouter(prefix="/charts", tags=["charts"])

_ONLINE_TRANSITIONS = {EventType.NEW_DEVICE.value, EventType.DEVICE_RETURNED.value}


_MAX_TIMELINE_POINTS = 600


@router.get("/online-timeline")
def online_timeline(hours: float = 24, db: Session = Depends(get_db)) -> dict:
    hours = max(0.25, min(hours, 24 * 90))
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=hours)

    current_online = db.execute(
        select(func.count()).select_from(Device).where(Device.is_online.is_(True))
    ).scalar_one()

    events = db.execute(
        select(DeviceEvent.timestamp, DeviceEvent.event_type)
        .where(
            DeviceEvent.timestamp >= window_start,
            DeviceEvent.event_type.in_([*_ONLINE_TRANSITIONS, EventType.DEVICE_OFFLINE.value]),
        )
        .order_by(DeviceEvent.timestamp.desc())
    ).all()

    # Walk backward from "now": undo each transition to reconstruct the online
    # count just before it happened. No snapshot table needed -- same idea as
    # the Network Time Machine (§13.1), scoped to one number.
    points = [(now, current_online)]
    running = current_online
    for ts, event_type in events:
        running += -1 if event_type in _ONLINE_TRANSITIONS else 1
        points.append((ts, running))
    points.append((window_start, running))
    points.reverse()

    # Many devices changing state in the same scan share one timestamp (e.g.
    # 80 devices returning after a power cut) -- keep only the final value
    # per instant instead of 80 stacked points.
    collapsed: list[tuple[datetime, int]] = []
    for ts, value in points:
        if collapsed and collapsed[-1][0] == ts:
            collapsed[-1] = (ts, value)
        else:
            collapsed.append((ts, value))
    points = collapsed

    # Long ranges (30/60 days) can hold thousands of transitions; collapse
    # them into fixed buckets keeping each bucket's min and max so dips and
    # peaks stay visible instead of being averaged away.
    if len(points) > _MAX_TIMELINE_POINTS:
        span = (now - window_start).total_seconds()
        n_buckets = _MAX_TIMELINE_POINTS // 2
        buckets: dict[int, list[int]] = {}
        for ts, value in points:
            idx = min(n_buckets - 1, int((ts - window_start).total_seconds() / span * n_buckets))
            buckets.setdefault(idx, []).append(value)
        reduced = []
        for idx in sorted(buckets):
            values = buckets[idx]
            t0 = window_start + timedelta(seconds=span * idx / n_buckets)
            t1 = window_start + timedelta(seconds=span * (idx + 0.5) / n_buckets)
            reduced.append((t0, min(values)))
            reduced.append((t1, max(values)))
        reduced.append((now, current_online))
        points = reduced

    return {
        "points": [{"timestamp": ts.isoformat(), "online": v} for ts, v in points],
        "start": window_start.isoformat(),
        "end": now.isoformat(),
    }


@router.get("/new-devices-daily")
def new_devices_daily(days: int = 30, db: Session = Depends(get_db)) -> dict:
    """Counts per *local* calendar day (the LXC runs in UTC, so grouping on
    the raw timestamp put devices found after 23:00/00:00 local on the wrong
    day). Days without new devices are included as 0, so the bars sit on a
    real calendar axis instead of skipping empty days."""
    days = max(1, min(days, 365))
    tz = local_timezone(db)
    tz_name = getattr(tz, "key", "UTC")
    today = datetime.now(tz).date()
    first_day = today - timedelta(days=days - 1)
    window_start = datetime.combine(first_day, datetime.min.time(), tzinfo=tz)

    local_day = func.date(func.timezone(tz_name, DeviceEvent.timestamp))
    rows = db.execute(
        select(local_day, func.count())
        .where(DeviceEvent.event_type == EventType.NEW_DEVICE.value, DeviceEvent.timestamp >= window_start)
        .group_by(local_day)
    ).all()
    counts = {d: c for d, c in rows}
    return {
        "points": [
            {"date": str(first_day + timedelta(days=i)), "count": counts.get(first_day + timedelta(days=i), 0)}
            for i in range(days)
        ]
    }


@router.get("/connection-split")
def connection_split(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(Device.connection_type, func.count()).group_by(Device.connection_type)).all()
    return {"items": [{"label": c or "Nepoznato", "count": n} for c, n in rows]}


@router.get("/device-types")
def device_types(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(Device.device_type, func.count()).group_by(Device.device_type)).all()
    return {"items": [{"label": t or "Nepoznato", "count": n} for t, n in rows]}


@router.get("/top-vendors")
def top_vendors(limit: int = 8, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(Device.vendor, func.count())
        .where(Device.vendor.is_not(None))
        .group_by(Device.vendor)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return {"items": [{"label": v, "count": n} for v, n in rows]}
