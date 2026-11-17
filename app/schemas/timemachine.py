from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TimeMachineDeviceOut(BaseModel):
    device_id: int
    mac_address: str
    ip_address: str | None
    hostname: str | None
    vendor: str | None
    custom_name: str | None
    online: bool
    status_changed_at: datetime
    first_seen: datetime


class TimeMachineResponse(BaseModel):
    at: datetime
    devices: list[TimeMachineDeviceOut]
    online_count: int
    offline_count: int
    appeared_since: list[str]
    disappeared_since: list[str]


class TimeMachineBounds(BaseModel):
    earliest: datetime | None
    latest: datetime
