from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from app.database import SessionLocal
from app.services import notification_log
from app.services.notification_gate import block_reason
from app.services.settings_store import get_setting

logger = logging.getLogger("networkwatcher.webhook")

_WIRED_EVENT_TYPES = {
    "NEW_DEVICE",
    "DEVICE_OFFLINE",
    "DEVICE_RETURNED",
    "ANOMALY_BURST_NEW_DEVICES",
    "VENDOR_MISMATCH",
    "IP_CONFLICT",
    "SCAN_DETECTED",
}


def _load_config(db) -> dict | None:
    if not get_setting(db, "webhook", "enabled", False):
        return None
    url = get_setting(db, "webhook", "url", None)
    if not url:
        return None
    return {"url": url, "headers": get_setting(db, "webhook", "headers", {})}


def _post(url: str, headers: dict, payload: dict) -> tuple[bool, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)


def publish_event(event_type: str, mac: str | None, ip: str | None, extra: dict | None = None) -> None:
    """§18.1. Never raises -- must not block detection (§36)."""
    if event_type not in _WIRED_EVENT_TYPES:
        return
    db = SessionLocal()
    try:
        config = _load_config(db)
        reason = block_reason(db, mac, event_type) if config is not None else None
    finally:
        db.close()
    if config is None:
        return
    destination = notification_log.safe_url(config["url"])
    if reason:
        notification_log.record("WEBHOOK", event_type, mac, destination, notification_log.SKIPPED, reason)
        return

    ok, message = _post(config["url"], config["headers"], {"event": event_type, "mac": mac, "ip": ip, **(extra or {})})
    if not ok:
        logger.warning("Webhook publish failed (event=%s mac=%s): %s", event_type, mac, message)
    notification_log.record(
        "WEBHOOK",
        event_type,
        mac,
        destination,
        notification_log.SUCCESS if ok else notification_log.FAILED,
        None if ok else message,
    )


def test_connection() -> tuple[bool, str]:
    db = SessionLocal()
    try:
        config = _load_config(db)
    finally:
        db.close()
    if config is None:
        return False, "Webhook URL nije podešen"

    return _post(config["url"], config["headers"], {"event": "TEST", "message": "Network Device Watcher test"})
