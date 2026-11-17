from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.services.settings_store import get_setting

logger = logging.getLogger("networkwatcher.notifications")

DEFAULT_TIMEZONE = "Europe/Belgrade"


def local_timezone(db) -> ZoneInfo | timezone:
    """User-facing wall-clock timezone. The LXC itself runs in UTC, so plain
    datetime.now() would put quiet hours 1-2h off from what the user typed
    (23:00 local != 23:00 UTC)."""
    name = get_setting(db, "notifications", "timezone", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Unknown timezone %r, falling back to UTC", name)
        return timezone.utc


def is_quiet_hours_now(db, now: datetime | None = None) -> bool:
    """§9.1 -- events are always logged, but SMTP/MQTT/webhook
    notifications are suppressed during the configured quiet window.
    """
    if not get_setting(db, "notifications", "quiet_hours_enabled", False):
        return False

    start_str = get_setting(db, "notifications", "quiet_hours_start", "23:00")
    end_str = get_setting(db, "notifications", "quiet_hours_end", "07:00")
    try:
        start = time.fromisoformat(start_str)
        end = time.fromisoformat(end_str)
    except ValueError:
        return False

    tz = local_timezone(db)
    current = (now.astimezone(tz) if now else datetime.now(tz)).time()
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end  # window wraps past midnight


def is_device_trusted(db, mac: str | None) -> bool:
    if not mac:
        return False
    from app.models.device import Device

    trusted = db.execute(select(Device.is_trusted).where(Device.mac_address == mac)).scalar_one_or_none()
    return bool(trusted)


# Security anomalies are reported even for trusted devices: "trusted" means
# "don't bother me about this device coming and going" (§12), not
# "ignore it if it starts sweeping the network or its MAC/IP looks spoofed".
# Legitimate scanners belong on the scan-detection ignore list instead.
ANOMALY_EVENTS = {"SCAN_DETECTED", "IP_CONFLICT", "VENDOR_MISMATCH", "ANOMALY_BURST_NEW_DEVICES"}


def should_notify(db, mac: str | None = None, event_type: str | None = None) -> bool:
    """Single gate for every external notification channel (SMTP/MQTT event
    topics/webhook): not during quiet hours (§9.1), and not for a
    trusted device (§12) unless it's a security anomaly. Detection
    and event logging are unaffected.
    """
    return block_reason(db, mac, event_type) is None


def block_reason(db, mac: str | None = None, event_type: str | None = None) -> str | None:
    """Why an external notification is suppressed (shown in notification_log), or None."""
    if is_quiet_hours_now(db):
        return "tiha zona"
    if event_type not in ANOMALY_EVENTS and is_device_trusted(db, mac):
        return "poverljiv uređaj"
    return None
