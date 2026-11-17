from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.device import DeviceEventOut, DeviceOut


class StatsOut(BaseModel):
    total_devices: int
    online: int
    offline: int
    new_devices: int
    wifi_devices: int
    lan_devices: int
    active_ip_conflicts: int
    active_scans_detected: int
    sniffer_status: str = "UNKNOWN"
    last_device: DeviceOut | None
    last_events: list[DeviceEventOut]
    last_scan_at: datetime | None
    scanner_status: str
    database_status: str
    mqtt_status: str
    smtp_status: str
    webhook_status: str
    omada_status: str
