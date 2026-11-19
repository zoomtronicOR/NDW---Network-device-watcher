""""Special" devices (Settings -> Special): MACs the user wants a notification
for whenever they come online or go offline -- on every configured channel,
also when the device is trusted, and optionally also during quiet hours."""

from __future__ import annotations

import logging

from app.models.device import Device
from app.services import notification_log
from app.services.broadcast_client import broadcast_anomaly
from app.services.notification_gate import is_quiet_hours_now
from app.services.settings_store import get_setting

logger = logging.getLogger("networkwatcher.special")

SPECIAL_EVENT = "SPECIAL_DEVICE"


def special_macs(db) -> set[str]:
    return {m.upper() for m in (get_setting(db, "special", "macs", []) or [])}


def notify_special(db, device: Device, online: bool, mqtt_publisher, webhook_publish_event) -> None:
    """Send the special-device notification on all channels. Never raises."""
    try:
        state = "online" if online else "offline"
        name = device.custom_name or device.hostname or device.mac_address
        quiet = is_quiet_hours_now(db) and not get_setting(db, "special", "ignore_quiet_hours", False)
        extra = {"state": state, "name": name}

        # Browser toast always (like every UI event, quiet hours don't apply).
        broadcast_anomaly(
            {"event_type": SPECIAL_EVENT, "mac": device.mac_address, "ip": device.ip_address, "name": name, "online": online}
        )
        if quiet:
            for channel in ("MQTT", "WEBHOOK", "SMTP"):
                notification_log.record(channel, SPECIAL_EVENT, device.mac_address, "-", notification_log.SKIPPED, "tiha zona")
            return

        mqtt_publisher.publish_special(device.mac_address, device.ip_address, extra)
        webhook_publish_event(SPECIAL_EVENT, device.mac_address, device.ip_address, extra, force=True)
        _send_email(db, device, name, online)
    except Exception:
        logger.exception("special device notification failed")


def _send_email(db, device: Device, name: str, online: bool) -> None:
    from app.services.smtp_client import _load_config, _send

    config = _load_config(db)
    if config is None or not config["recipients"]:
        return
    subject = f"{name} je {'online' if online else 'offline'}"
    body = (
        f"Poseban uređaj {'se prijavio na mrežu' if online else 'je napustio mrežu'}.\n\n"
        f"Naziv: {name}\nIP: {device.ip_address or '-'}\nMAC: {device.mac_address}\n"
        f"Vendor: {device.vendor or '-'}\nVeza: {device.connection_type or '-'}\n"
    )
    for recipient in config["recipients"]:
        try:
            _send(config, subject, body, [recipient])
            notification_log.record("SMTP", SPECIAL_EVENT, device.mac_address, recipient, notification_log.SUCCESS)
        except Exception as e:
            notification_log.record("SMTP", SPECIAL_EVENT, device.mac_address, recipient, notification_log.FAILED, str(e))

