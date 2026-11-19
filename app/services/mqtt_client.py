from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from app.database import SessionLocal
from app.services.crypto import decrypt
from app.services.ha_discovery import publish_discovery
from app.services import notification_log
from app.services.notification_gate import block_reason
from app.services.settings_store import get_setting, set_setting

logger = logging.getLogger("networkwatcher.mqtt")

_EVENT_TOPIC = {
    "NEW_DEVICE": "events/new_device",
    "DEVICE_OFFLINE": "events/offline",
    "DEVICE_RETURNED": "events/returned",
    "SCAN_DETECTED": "events/scan_detected",
    "IP_CONFLICT": "events/ip_conflict",
}
_RETRY_SECONDS = 60

# Events that change a single device's online/offline state topic.
_STATE_EVENTS = {"NEW_DEVICE", "DEVICE_OFFLINE", "DEVICE_RETURNED"}


def _normalize_mac(mac: str) -> str:
    return mac.lower().replace(":", "_")


def _load_config(db) -> dict | None:
    if not get_setting(db, "mqtt", "enabled", False):
        return None
    host = get_setting(db, "mqtt", "host", None)
    if not host:
        return None
    password_enc = get_setting(db, "mqtt", "password", None)
    return {
        "host": host,
        "port": get_setting(db, "mqtt", "port", 1883),
        "username": get_setting(db, "mqtt", "username", None),
        "password": decrypt(password_enc) if password_enc else None,
        "tls_enabled": get_setting(db, "mqtt", "tls_enabled", False),
        "client_id": get_setting(db, "mqtt", "client_id", "networkwatcher"),
        "base_topic": get_setting(db, "mqtt", "base_topic", "networkwatcher"),
        "qos": get_setting(db, "mqtt", "qos", 0),
        "retain": get_setting(db, "mqtt", "retain", True),
        "ha_discovery_enabled": get_setting(db, "mqtt", "ha_discovery_enabled", False),
        "ha_discovery_prefix": get_setting(db, "mqtt", "ha_discovery_prefix", "homeassistant"),
    }


class MqttPublisher:
    """Thin, optional MQTT publisher (§14/15/36).

    MQTT must never block device detection: every public method here
    catches its own errors, logs, and returns -- callers don't need to
    guard against MQTT being unset or the broker being unreachable.
    """

    def __init__(self, role: str | None = None) -> None:
        # role=None is the scanner's main publisher (owns the status/LWT and
        # HA discovery). Any other process (e.g. "sniffer") gets its own
        # client ID -- a broker disconnects the older of two clients sharing
        # one ID, so they would keep kicking each other off -- and never
        # touches the shared status topic.
        self._role = role
        self._client: mqtt.Client | None = None
        self._config: dict | None = None
        self._lock = threading.Lock()
        self._retry_after = 0.0
        self._last_success_write = 0.0

    def _ensure_client(self) -> mqtt.Client | None:
        db = SessionLocal()
        try:
            config = _load_config(db)
        finally:
            db.close()

        if config is None:
            self._disconnect()
            return None

        with self._lock:
            if self._client is not None and self._config == config:
                if self._client.is_connected():
                    self._record_success()
                return self._client

            self._disconnect()

            # Backoff: with the broker down, every publish call in a scan
            # cycle used to retry a blocking connect (~5s each) -- dozens of
            # events could stall detection for minutes (violates §36).
            if time.monotonic() < self._retry_after:
                return None

            client_id = config["client_id"] + (f"-{self._role}" if self._role else "")
            client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
            if config["username"]:
                client.username_pw_set(config["username"], config["password"])
            if config["tls_enabled"]:
                client.tls_set()
            if not self._role:
                client.will_set(f"{config['base_topic']}/status", "offline", qos=config["qos"], retain=True)

            try:
                client.connect(config["host"], config["port"], keepalive=30)
                client.loop_start()
                if not self._role:
                    client.publish(f"{config['base_topic']}/status", "online", qos=config["qos"], retain=True)
                if config["ha_discovery_enabled"] and not self._role:
                    publish_discovery(client, config["ha_discovery_prefix"], config["base_topic"], config["qos"])
            except Exception as e:
                logger.warning("MQTT connect failed (host=%s): %s -- retry in %ds", config["host"], e, _RETRY_SECONDS)
                self._retry_after = time.monotonic() + _RETRY_SECONDS
                return None

            self._client = client
            self._config = config
            self._record_success()
            return client

    def _record_success(self) -> None:
        # Dashboard health strip freshness check (§35), same pattern
        # as omada_status's last_sync_at. Throttled: this ran on every single
        # publish call (a DB write per event).
        if time.monotonic() - self._last_success_write < 10:
            return
        self._last_success_write = time.monotonic()
        db = SessionLocal()
        try:
            set_setting(db, "mqtt", "last_success_at", datetime.now(timezone.utc).isoformat())
        finally:
            db.close()

    def _disconnect(self) -> None:
        if self._client is None:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass
        self._client = None
        self._config = None

    def publish_event(self, event_type: str, mac: str, ip: str | None, extra: dict | None = None) -> None:
        """Two kinds of topics are written here, and only one of them is a
        "notification":

        * events/<type>  -- a push notification; suppressed during quiet hours
          and for trusted devices (§9.1 / 12).
        * device/<mac>/status|ip -- retained *state*. Always published, even in
          quiet hours: suppressing it left Home Assistant showing stale
          online/offline states during and after the quiet window, which
          looked like the scanner had stopped working.
        """
        try:
            db = SessionLocal()
            try:
                reason = block_reason(db, mac, event_type)
                enabled_config = _load_config(db)
            finally:
                db.close()

            client = self._ensure_client()
            config = self._config or enabled_config

            suffix = _EVENT_TOPIC.get(event_type)
            if suffix and enabled_config is not None:
                topic = f"{enabled_config['base_topic']}/{suffix}"
                if reason:
                    notification_log.record("MQTT", event_type, mac, topic, notification_log.SKIPPED, reason)
                elif client is None:
                    notification_log.record(
                        "MQTT", event_type, mac, topic, notification_log.FAILED, "MQTT broker nije dostupan"
                    )
                else:
                    payload = json.dumps({"mac": mac, "ip": ip, "event": event_type, **(extra or {})})
                    info = client.publish(topic, payload, qos=config["qos"], retain=False)
                    ok = info.rc == mqtt.MQTT_ERR_SUCCESS
                    notification_log.record(
                        "MQTT",
                        event_type,
                        mac,
                        topic,
                        notification_log.SUCCESS if ok else notification_log.FAILED,
                        None if ok else mqtt.error_string(info.rc),
                    )

            if client is None:
                return

            if event_type not in _STATE_EVENTS:
                return

            norm_mac = _normalize_mac(mac)
            status = "offline" if event_type == "DEVICE_OFFLINE" else "online"
            client.publish(
                f"{config['base_topic']}/device/{norm_mac}/status", status, qos=config["qos"], retain=config["retain"]
            )
            if ip:
                client.publish(
                    f"{config['base_topic']}/device/{norm_mac}/ip", ip, qos=config["qos"], retain=config["retain"]
                )
        except Exception:
            logger.exception("MQTT publish_event failed")

    def publish_special(self, mac: str, ip: str | None, extra: dict) -> None:
        """Special-device notification (Settings -> Special): events/special.
        The caller already applied the quiet-hours rule; trusted is ignored."""
        try:
            client = self._ensure_client()
            config = self._config
            if client is None or config is None:
                db = SessionLocal()
                try:
                    enabled = _load_config(db) is not None
                finally:
                    db.close()
                if enabled:
                    notification_log.record("MQTT", "SPECIAL_DEVICE", mac, "events/special", notification_log.FAILED, "MQTT broker nije dostupan")
                return
            topic = f"{config['base_topic']}/events/special"
            payload = json.dumps({"mac": mac, "ip": ip, "event": "SPECIAL_DEVICE", **extra})
            info = client.publish(topic, payload, qos=config["qos"], retain=False)
            ok = info.rc == mqtt.MQTT_ERR_SUCCESS
            notification_log.record(
                "MQTT", "SPECIAL_DEVICE", mac, topic,
                notification_log.SUCCESS if ok else notification_log.FAILED, None if ok else mqtt.error_string(info.rc),
            )
        except Exception:
            logger.exception("MQTT publish_special failed")

    def publish_stats(self, stats: dict) -> None:
        try:
            client = self._ensure_client()
            if client is None:
                return
            config = self._config
            for key, value in stats.items():
                client.publish(
                    f"{config['base_topic']}/stats/{key}", str(value), qos=config["qos"], retain=config["retain"]
                )
        except Exception:
            logger.exception("MQTT publish_stats failed")

    def publish_devices_snapshot(self, devices: list[dict]) -> None:
        try:
            client = self._ensure_client()
            if client is None:
                return
            config = self._config
            client.publish(
                f"{config['base_topic']}/devices", json.dumps(devices), qos=config["qos"], retain=config["retain"]
            )
        except Exception:
            logger.exception("MQTT publish_devices_snapshot failed")


mqtt_publisher = MqttPublisher()


def test_connection() -> tuple[bool, str]:
    db = SessionLocal()
    try:
        host = get_setting(db, "mqtt", "host", None)
        if not host:
            return False, "Broker host nije podešen"
        port = get_setting(db, "mqtt", "port", 1883)
        username = get_setting(db, "mqtt", "username", None)
        password_enc = get_setting(db, "mqtt", "password", None)
        password = decrypt(password_enc) if password_enc else None
        tls_enabled = get_setting(db, "mqtt", "tls_enabled", False)
        client_id = get_setting(db, "mqtt", "client_id", "networkwatcher") + "-test"
        base_topic = get_setting(db, "mqtt", "base_topic", "networkwatcher")
    finally:
        db.close()

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    if username:
        client.username_pw_set(username, password)
    if tls_enabled:
        client.tls_set()

    result: dict = {"connected": False, "error": None}

    def on_connect(_client, _userdata, _flags, rc):
        result["connected"] = rc == 0
        if rc != 0:
            result["error"] = mqtt.connack_string(rc)

    client.on_connect = on_connect

    try:
        client.connect(host, port, keepalive=5)
        client.loop_start()
        for _ in range(50):
            if result["connected"] or result["error"]:
                break
            time.sleep(0.1)
        if result["connected"]:
            client.publish(f"{base_topic}/status", "test", qos=0, retain=False)
        client.loop_stop()
        client.disconnect()
    except Exception as e:
        return False, f"Greška pri povezivanju: {e}"

    if result["connected"]:
        return True, "MQTT konekcija uspešna"
    return False, result["error"] or "Konekcija nije uspela (timeout)"
