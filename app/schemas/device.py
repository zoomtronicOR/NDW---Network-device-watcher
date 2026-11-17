from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.device import Device
from app.models.device_event import DeviceEvent
from app.models.ip_history import IpHistory


def compute_status(device: Device) -> str:
    if device.is_new:
        return "NEW"
    return "ONLINE" if device.is_online else "OFFLINE"


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mac_address: str
    ip_address: str | None
    ipv6_address: str | None
    hostname: str | None
    dhcp_hostname: str | None
    mdns_hostname: str | None
    netbios_hostname: str | None
    vendor: str | None
    device_type: str | None
    connection_type: str | None
    interface: str | None
    wifi_ssid: str | None
    wifi_rssi: int | None
    gateway: str | None
    vlan: int | None
    switch_port: str | None
    os_fingerprint: str | None
    first_seen: datetime
    last_seen: datetime
    is_online: bool
    is_new: bool
    is_trusted: bool
    hostname_locked: bool = False
    vendor_locked: bool = False
    device_type_auto: bool = False
    seen_count: int
    custom_name: str | None
    notes: str | None
    status: str

    @classmethod
    def from_device(cls, device: Device) -> "DeviceOut":
        data = {c.name: getattr(device, c.name) for c in device.__table__.columns}
        data["status"] = compute_status(device)
        return cls(**data)


class DeviceUpdate(BaseModel):
    custom_name: str | None = None
    hostname: str | None = None
    vendor: str | None = None
    device_type: str | None = None
    notes: str | None = None
    is_trusted: bool | None = None


class DeviceListResponse(BaseModel):
    items: list[DeviceOut]
    total: int


class IpHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ip_address: str
    first_seen: datetime
    last_seen: datetime


class DeviceEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    event_type: str
    ip_address: str | None
    timestamp: datetime
    details: str | None
    device_mac: str | None = None
    device_name: str | None = None
    device_vendor: str | None = None
    device_connection_type: str | None = None
    device_type: str | None = None
    device_is_trusted: bool | None = None


class DeviceDetailOut(DeviceOut):
    ip_history: list[IpHistoryOut]
    events: list[DeviceEventOut]

    @classmethod
    def from_device_detail(
        cls, device: Device, ip_history: list[IpHistory], events: list[DeviceEvent]
    ) -> "DeviceDetailOut":
        data = {c.name: getattr(device, c.name) for c in device.__table__.columns}
        data["status"] = compute_status(device)
        data["ip_history"] = [IpHistoryOut.model_validate(h) for h in ip_history]
        data["events"] = [DeviceEventOut.model_validate(e) for e in events]
        return cls(**data)
