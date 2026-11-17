"""networkwatcher-sniffer -- passive ARP listener (§8.2 / 8.3).

The only process in the app that needs CAP_NET_RAW (granted to this one
systemd unit via AmbientCapabilities, not to the scanner or web service --
§38). It never sends anything: it opens an AF_PACKET socket that the
kernel already filters to ARP frames (ethertype 0x0806), so no other traffic
is ever copied into the process.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import time
from datetime import datetime, timedelta, timezone
from types import FrameType

from sqlalchemy import select

from app.database import SessionLocal
from app.models.device import Device
from app.models.device_event import DeviceEvent
from app.models.enums import EventType
from app.services.arp_monitor import (
    ETH_P_ARP,
    ArpMonitor,
    ArpMonitorConfig,
    ConflictAlert,
    ScanAlert,
    ScannerProfile,
    parse_arp_frame,
)
from app.services.broadcast_client import broadcast_anomaly
from app.services.mqtt_client import MqttPublisher
from app.services.settings_store import get_setting, set_setting
from app.services.webhook_client import publish_event as webhook_publish_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("networkwatcher.sniffer")

PACKET_OUTGOING = 4
_SETTINGS_RELOAD_SECONDS = 30
_PENDING_MAX_AGE_SECONDS = 180

_running = True
mqtt_publisher = MqttPublisher(role="sniffer")

SCAN_DETECTION_DEFAULTS = {
    "enabled": True,
    "threshold_hosts": 30,
    "window_seconds": 60,
    "ip_conflict_enabled": True,
    "conflict_window_seconds": 600,
    "cooldown_seconds": 600,
    "ignore_macs": [],
}


def _handle_stop(signum: int, frame: FrameType | None) -> None:
    global _running
    _running = False


def _own_macs() -> set[str]:
    macs = set()
    try:
        for iface in os.listdir("/sys/class/net"):
            try:
                with open(f"/sys/class/net/{iface}/address") as f:
                    macs.add(f.read().strip().upper())
            except OSError:
                continue
    except OSError:
        pass
    return macs


def _load_config(db) -> tuple[ArpMonitorConfig, str | None]:
    def g(key):
        return get_setting(db, "scan_detection", key, SCAN_DETECTION_DEFAULTS[key])

    config = ArpMonitorConfig(
        scan_enabled=bool(g("enabled")),
        scan_threshold=max(2, int(g("threshold_hosts"))),
        scan_window_seconds=max(5, int(g("window_seconds"))),
        conflict_enabled=bool(g("ip_conflict_enabled")),
        # Hosts broadcast ARP rarely (refreshes are unicast, invisible here), so
        # two conflicting hosts' claims are usually minutes apart -- a 60s
        # window almost never saw both.
        conflict_window_seconds=max(60, int(g("conflict_window_seconds"))),
        cooldown_seconds=max(30, int(g("cooldown_seconds"))),
        ignore_macs={m.strip().upper() for m in (g("ignore_macs") or []) if m.strip()},
    )
    interface = get_setting(db, "scanner", "interface", None)
    return config, interface


def _open_socket(interface: str | None) -> socket.socket:
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ARP))
    if interface:
        sock.bind((interface, 0))
    sock.settimeout(1.0)
    return sock


def _recently_recorded(db, device_id: int, event_type: str, cooldown_seconds: int) -> bool:
    """Cooldown backed by the DB, not just memory: the in-process cooldown
    reset on every service restart, producing duplicate alerts minutes apart."""
    since = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
    return (
        db.execute(
            select(DeviceEvent.id)
            .where(
                DeviceEvent.device_id == device_id,
                DeviceEvent.event_type == event_type,
                DeviceEvent.timestamp >= since,
            )
            .limit(1)
        ).first()
        is not None
    )


def _emit_scan(db, alert: ScanAlert, devices: dict[str, Device], cooldown_seconds: int) -> bool:
    device = devices.get(alert.mac)
    if device is None:
        return False
    if _recently_recorded(db, device.id, EventType.SCAN_DETECTED.value, cooldown_seconds):
        return True  # already reported within the cooldown window
    ip = alert.ip or device.ip_address
    details = {
        "source_mac": alert.mac,
        "source_ip": ip,
        "target_count": alert.target_count,
        "window_seconds": alert.window_seconds,
        "method": "ARP sweep",
    }
    if alert.known_scanner:
        details["known_scanner"] = True
        details["reason"] = alert.reason
    db.add(
        DeviceEvent(
            device_id=device.id,
            event_type=EventType.SCAN_DETECTED.value,
            ip_address=ip,
            timestamp=datetime.now(timezone.utc),
            details=json.dumps(details),
        )
    )
    db.commit()
    logger.warning(
        "SCAN_DETECTED: %s (%s) probed %d hosts in %ds%s",
        alert.mac,
        ip,
        alert.target_count,
        alert.window_seconds,
        f" -- known scanner, unusual: {alert.reason}" if alert.known_scanner else "",
    )

    extra = {"target_count": alert.target_count, "window_seconds": alert.window_seconds}
    if alert.known_scanner:
        extra["reason"] = alert.reason
    mqtt_publisher.publish_event("SCAN_DETECTED", alert.mac, ip, extra)
    webhook_publish_event("SCAN_DETECTED", alert.mac, ip, extra)
    broadcast_anomaly(
        {
            "event_type": "SCAN_DETECTED",
            "mac": alert.mac,
            "ip": ip,
            "name": device.custom_name or device.hostname,
            "vendor": device.vendor,
            **extra,
        }
    )
    return True


def _emit_conflict(db, alert: ConflictAlert, devices: dict[str, Device], cooldown_seconds: int) -> bool:
    known = [devices[m] for m in alert.macs if m in devices]
    if not known:
        return False
    # Same per-IP cooldown as the scanner-side detector, so one conflict seen
    # by both sources is reported once.
    since = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
    already = db.execute(
        select(DeviceEvent.id)
        .where(
            DeviceEvent.event_type == EventType.IP_CONFLICT.value,
            DeviceEvent.ip_address == alert.ip,
            DeviceEvent.timestamp >= since,
        )
        .limit(1)
    ).first()
    if already is not None:
        return True
    now = datetime.now(timezone.utc)
    for device in known:
        others = [m for m in alert.macs if m != device.mac_address]
        db.add(
            DeviceEvent(
                device_id=device.id,
                event_type=EventType.IP_CONFLICT.value,
                ip_address=alert.ip,
                timestamp=now,
                details=json.dumps({"ip": alert.ip, "conflicting_macs": others, "source": "ARP"}),
            )
        )
    db.commit()
    logger.warning("IP_CONFLICT: %s claimed by %s", alert.ip, ", ".join(alert.macs))

    extra = {"conflicting_macs": alert.macs}
    for mac in alert.macs:
        mqtt_publisher.publish_event("IP_CONFLICT", mac, alert.ip, extra)
        webhook_publish_event("IP_CONFLICT", mac, alert.ip, extra)
    broadcast_anomaly({"event_type": "IP_CONFLICT", "ip": alert.ip, "macs": alert.macs})
    return True


def _load_profiles(db) -> dict[str, ScannerProfile]:
    raw = get_setting(db, "scan_detection", "profiles", {}) or {}
    profiles = {}
    for mac, data in raw.items():
        try:
            profiles[mac] = ScannerProfile.from_dict(data)
        except Exception:
            continue
    return profiles


def _save_profiles(db, monitor: ArpMonitor) -> None:
    hour = int(time.time() // 3600)
    for prof in monitor.profiles.values():
        prof.prune(hour)
    set_setting(db, "scan_detection", "profiles", {m: p.to_dict() for m, p in monitor.profiles.items()})


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    logger.info("networkwatcher-sniffer starting")
    db = SessionLocal()
    try:
        config, interface = _load_config(db)
    finally:
        db.close()

    own = _own_macs()
    db = SessionLocal()
    try:
        profiles = _load_profiles(db)
    finally:
        db.close()
    monitor = ArpMonitor(config, own, profiles)
    sock = _open_socket(interface)
    logger.info("listening for ARP on %s (own MACs ignored: %s)", interface or "all interfaces", ", ".join(sorted(own)))

    pending: list[tuple[float, ScanAlert | ConflictAlert]] = []
    last_reload = time.monotonic()
    last_tick = last_reload
    packets = 0

    while _running:
        try:
            frame, addr = sock.recvfrom(2048)
        except socket.timeout:
            frame, addr = None, None
        except OSError:
            logger.exception("socket error, reopening")
            time.sleep(2)
            sock.close()
            sock = _open_socket(interface)
            continue

        now = time.monotonic()
        wall = time.time()
        if frame is not None and addr[2] != PACKET_OUTGOING:
            pkt = parse_arp_frame(frame)
            if pkt is not None:
                packets += 1
                for alert in monitor.observe(pkt, now, wall):
                    pending.append((now, alert))
        if now - last_tick >= 1:
            last_tick = now
            for alert in monitor.tick(now, wall):
                pending.append((now, alert))

        if pending:
            db = SessionLocal()
            try:
                devices = {d.mac_address: d for d in db.execute(select(Device)).scalars()}
                still_pending = []
                for created, alert in pending:
                    emit = _emit_scan if isinstance(alert, ScanAlert) else _emit_conflict
                    try:
                        done = emit(db, alert, devices, monitor.config.cooldown_seconds)
                    except Exception:
                        logger.exception("failed to record %s", alert)
                        db.rollback()
                        done = True
                    # Source not in the devices table yet -- the scanner will
                    # add it within one cycle; retry instead of dropping it.
                    if not done and now - created < _PENDING_MAX_AGE_SECONDS:
                        still_pending.append((created, alert))
                    elif not done:
                        logger.warning("dropping alert for unknown device: %s", alert)
                pending = still_pending
            finally:
                db.close()

        if now - last_reload >= _SETTINGS_RELOAD_SECONDS:
            last_reload = now
            monitor.prune(now)
            new_interface = interface
            db = SessionLocal()
            try:
                new_config, new_interface = _load_config(db)
                monitor.config = new_config
                set_setting(db, "scan_detection", "last_heartbeat_at", datetime.now(timezone.utc).isoformat())
                set_setting(db, "scan_detection", "packets_seen", packets)
                _save_profiles(db, monitor)
            except Exception:
                logger.exception("settings reload failed")
            finally:
                db.close()
            if new_interface != interface:
                interface = new_interface
                sock.close()
                sock = _open_socket(interface)
                logger.info("interface changed, now listening on %s", interface or "all interfaces")

    sock.close()
    db = SessionLocal()
    try:
        _save_profiles(db, monitor)
    except Exception:
        logger.exception("could not save scanner profiles")
    finally:
        db.close()
    logger.info("networkwatcher-sniffer stopped")


if __name__ == "__main__":
    main()
