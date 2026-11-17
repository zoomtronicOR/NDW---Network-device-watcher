from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.device import Device
from app.models.device_event import DeviceEvent
from app.models.enums import ConnectionType, EventType
from app.schemas.device import DeviceEventOut, DeviceOut
from app.schemas.stats import StatsOut
from app.services.settings_store import get_setting

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)) -> StatsOut:
    total = db.execute(select(func.count()).select_from(Device)).scalar_one()
    online = db.execute(select(func.count()).select_from(Device).where(Device.is_online.is_(True))).scalar_one()
    new_devices = db.execute(select(func.count()).select_from(Device).where(Device.is_new.is_(True))).scalar_one()
    wifi = db.execute(
        select(func.count()).select_from(Device).where(Device.connection_type == ConnectionType.WIFI.value)
    ).scalar_one()
    lan = db.execute(
        select(func.count()).select_from(Device).where(Device.connection_type == ConnectionType.LAN.value)
    ).scalar_one()

    now = datetime.now(timezone.utc)

    conflict_window = now - timedelta(minutes=15)
    active_ip_conflicts = db.execute(
        select(func.count(func.distinct(DeviceEvent.ip_address))).where(
            DeviceEvent.event_type == EventType.IP_CONFLICT.value,
            DeviceEvent.timestamp >= conflict_window,
        )
    ).scalar_one()

    scan_window = now - timedelta(hours=24)
    active_scans = db.execute(
        select(func.count())
        .select_from(DeviceEvent)
        .where(
            DeviceEvent.event_type == EventType.SCAN_DETECTED.value,
            DeviceEvent.timestamp >= scan_window,
        )
    ).scalar_one()

    last_device = db.execute(select(Device).order_by(Device.first_seen.desc()).limit(1)).scalar_one_or_none()
    last_events = db.execute(select(DeviceEvent).order_by(DeviceEvent.timestamp.desc()).limit(10)).scalars().all()

    last_scan_at = db.execute(select(func.max(Device.last_seen))).scalar_one_or_none()
    scan_interval = get_setting(db, "scanner", "scan_interval_seconds", 30)
    if last_scan_at is None:
        scanner_status = "UNKNOWN"
    else:
        stale_after = timedelta(seconds=scan_interval * 3)
        scanner_status = "ONLINE" if (now - last_scan_at) <= stale_after else "OFFLINE"

    if not get_setting(db, "omada", "enabled", False) or not get_setting(db, "omada", "site_id", None):
        omada_status = "DISABLED"
    else:
        last_omada_sync = get_setting(db, "omada", "last_sync_at", None)
        if not last_omada_sync:
            omada_status = "OFFLINE"
        else:
            stale_after = timedelta(seconds=scan_interval * 3)
            omada_status = "ONLINE" if (now - datetime.fromisoformat(last_omada_sync)) <= stale_after else "OFFLINE"

    if not get_setting(db, "mqtt", "enabled", False) or not get_setting(db, "mqtt", "host", None):
        mqtt_status = "DISABLED"
    else:
        last_mqtt_success = get_setting(db, "mqtt", "last_success_at", None)
        if not last_mqtt_success:
            mqtt_status = "OFFLINE"
        else:
            stale_after = timedelta(seconds=scan_interval * 3)
            mqtt_status = "ONLINE" if (now - datetime.fromisoformat(last_mqtt_success)) <= stale_after else "OFFLINE"

    # SMTP/webhook only connect when an actual event fires (§18/18.1),
    # so there's no periodic connection to poll like MQTT/Omada -- §35's
    # own example shows SMTP as "CONFIGURED", not ONLINE/OFFLINE.
    if get_setting(db, "smtp", "enabled", False) and get_setting(db, "smtp", "host", None):
        smtp_status = "CONFIGURED"
    else:
        smtp_status = "DISABLED"

    if get_setting(db, "webhook", "enabled", False) and get_setting(db, "webhook", "url", None):
        webhook_status = "CONFIGURED"
    else:
        webhook_status = "DISABLED"

    # ARP sniffer (scan / IP-conflict detection) heartbeats every 30s.
    if not get_setting(db, "scan_detection", "enabled", True):
        sniffer_status = "DISABLED"
    else:
        heartbeat = get_setting(db, "scan_detection", "last_heartbeat_at", None)
        if not heartbeat:
            sniffer_status = "OFFLINE"
        else:
            fresh = (now - datetime.fromisoformat(heartbeat)) <= timedelta(seconds=120)
            sniffer_status = "ONLINE" if fresh else "OFFLINE"

    return StatsOut(
        total_devices=total,
        online=online,
        offline=total - online,
        new_devices=new_devices,
        wifi_devices=wifi,
        lan_devices=lan,
        active_ip_conflicts=active_ip_conflicts,
        active_scans_detected=active_scans,
        last_device=DeviceOut.from_device(last_device) if last_device else None,
        last_events=[DeviceEventOut.model_validate(e) for e in last_events],
        last_scan_at=last_scan_at,
        scanner_status=scanner_status,
        database_status="ONLINE",
        mqtt_status=mqtt_status,
        smtp_status=smtp_status,
        webhook_status=webhook_status,
        omada_status=omada_status,
        sniffer_status=sniffer_status,
    )
