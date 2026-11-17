from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    mac_address: Mapped[str] = mapped_column(String(17), unique=True, index=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    ipv6_address: Mapped[str | None] = mapped_column(String(45))

    hostname: Mapped[str | None] = mapped_column(String(255))
    dhcp_hostname: Mapped[str | None] = mapped_column(String(255))
    mdns_hostname: Mapped[str | None] = mapped_column(String(255))
    netbios_hostname: Mapped[str | None] = mapped_column(String(255))

    vendor: Mapped[str | None] = mapped_column(String(255))
    device_type: Mapped[str | None] = mapped_column(String(100))

    connection_type: Mapped[str | None] = mapped_column(String(10))
    interface: Mapped[str | None] = mapped_column(String(50))

    wifi_ssid: Mapped[str | None] = mapped_column(String(255))
    wifi_rssi: Mapped[int | None] = mapped_column(Integer)

    gateway: Mapped[str | None] = mapped_column(String(45))
    vlan: Mapped[int | None] = mapped_column(Integer)
    switch_port: Mapped[str | None] = mapped_column(String(50))
    os_fingerprint: Mapped[str | None] = mapped_column(String(255))

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Manual overrides (user typed the value): never overwritten by rDNS/OUI/Omada.
    hostname_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    vendor_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # device_type came from the classifier (may be refined); False = user-set or empty.
    device_type_auto: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    seen_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    consecutive_misses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    custom_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    events: Mapped[list["DeviceEvent"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    ip_history: Mapped[list["IpHistory"]] = relationship(back_populates="device", cascade="all, delete-orphan")
