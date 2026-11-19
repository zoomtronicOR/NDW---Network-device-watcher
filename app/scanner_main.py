from __future__ import annotations

import logging
import signal
import time
from types import FrameType

from sqlalchemy import select

from app.database import SessionLocal
from app.models.device import Device
from app.services.broadcast_client import broadcast_scan_result
from app.services.detector import DetectionEngine
from app.services.mqtt_client import mqtt_publisher
from app.services.name_enricher import NameEnricher
from app.services.device_classifier import apply_classification
from app.services.omada_client import apply_omada_clients, fetch_clients, fetch_infra_devices
from app.services.omada_client import is_configured as omada_is_configured
from app.services.scanner import NetworkScanner, ScanError
from app.services.settings_store import get_setting
from app.services.smtp_client import send_new_device_email
from app.services.webhook_client import publish_event as webhook_publish_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("networkwatcher.scanner")

_running = True


def _handle_stop(signum: int, frame: FrameType | None) -> None:
    global _running
    _running = False


def _send_notifications(db, summary) -> None:
    devices_by_mac = {d.mac_address: d for d in db.execute(select(Device)).scalars().all()}

    for mac, ip in summary.new_devices:
        mqtt_publisher.publish_event("NEW_DEVICE", mac, ip)
        webhook_publish_event("NEW_DEVICE", mac, ip)
        device = devices_by_mac.get(mac)
        if device is not None:
            send_new_device_email(db, device)
    for mac, ip in summary.returned:
        mqtt_publisher.publish_event("DEVICE_RETURNED", mac, ip)
        webhook_publish_event("DEVICE_RETURNED", mac, ip)
    for mac, ip in summary.went_offline:
        mqtt_publisher.publish_event("DEVICE_OFFLINE", mac, ip)
        webhook_publish_event("DEVICE_OFFLINE", mac, ip)

    # Anomalies (§8.1/8.2) -- same channels, same quiet-hours/trusted gate.
    for mac in summary.vendor_mismatch:
        device = devices_by_mac.get(mac)
        webhook_publish_event("VENDOR_MISMATCH", mac, device.ip_address if device else None)
    for mac in set(summary.ip_conflicts):
        device = devices_by_mac.get(mac)
        ip = device.ip_address if device else None
        mqtt_publisher.publish_event("IP_CONFLICT", mac, ip)
        webhook_publish_event("IP_CONFLICT", mac, ip)
    if summary.burst_anomaly:
        webhook_publish_event(
            "ANOMALY_BURST_NEW_DEVICES", None, None, {"new_devices": [m for m, _ in summary.new_devices]}
        )

    devices = list(devices_by_mac.values())
    snapshot = [
        {
            "mac": d.mac_address,
            "ip": d.ip_address,
            "status": "NEW" if d.is_new else ("ONLINE" if d.is_online else "OFFLINE"),
        }
        for d in devices
    ]
    mqtt_publisher.publish_devices_snapshot(snapshot)

    last_new = max(devices, key=lambda d: d.first_seen, default=None)
    mqtt_publisher.publish_stats(
        {
            "total": len(devices),
            "online": sum(1 for d in devices if d.is_online),
            "wifi": sum(1 for d in devices if d.connection_type == "WIFI"),
            "lan": sum(1 for d in devices if d.connection_type == "LAN"),
            "last_new_device": last_new.mac_address if last_new else "-",
            "new_device_flag": "ON" if any(d.is_new for d in devices) else "OFF",
        }
    )

    def _brief(mac: str, ip: str | None) -> dict:
        device = devices_by_mac.get(mac)
        return {
            "mac": mac,
            "ip": ip,
            "hostname": device.hostname if device else None,
            "vendor": device.vendor if device else None,
            "connection_type": device.connection_type if device else None,
        }

    broadcast_scan_result(
        new_devices=[_brief(mac, ip) for mac, ip in summary.new_devices],
        returned=[_brief(mac, ip) for mac, ip in summary.returned],
        went_offline=[_brief(mac, ip) for mac, ip in summary.went_offline],
        burst_anomaly=summary.burst_anomaly,
    )


def run_once() -> None:
    db = SessionLocal()
    try:
        networks = get_setting(db, "scanner", "network_ranges", ["192.168.1.0/24"])
        interface = get_setting(db, "scanner", "interface", None)
        settle_seconds = get_setting(db, "scanner", "settle_seconds", 1.5)
        resolve_hostnames = get_setting(db, "scanner", "resolve_hostnames", True)
        offline_threshold = get_setting(db, "scanner", "offline_threshold", 3)
        offline_grace_seconds = get_setting(db, "scanner", "offline_grace_seconds", 300)

        scanner = NetworkScanner(
            networks=networks,
            interface=interface,
            settle_seconds=settle_seconds,
            resolve_hostnames=resolve_hostnames,
        )
        try:
            results = scanner.scan()
        except ScanError as e:
            logger.warning("scan failed, skipping this cycle (no device marked offline): %s", e)
            return

        # Omada first: its associated-client list doubles as a presence
        # signal for Wi-Fi devices that skipped this cycle's ARP probe.
        omada_clients = fetch_clients(db)
        omada_infra = fetch_infra_devices(db) if omada_clients is not None else {}

        engine = DetectionEngine(
            db,
            offline_threshold=offline_threshold,
            offline_grace_seconds=offline_grace_seconds,
            manage_connection_type=not omada_is_configured(db),
        )
        summary = engine.process_scan(results, present_macs=set(omada_clients or {}))

        wifi_enriched = (
            apply_omada_clients(
                db,
                omada_clients,
                {r.mac for r in results},
                infra=omada_infra,
                vendor_mismatch_out=summary.vendor_mismatch,
            )
            if omada_clients is not None
            else 0
        )

        try:
            typed = apply_classification(db, omada_clients, omada_infra)
            if typed:
                logger.info("device type auto-classified for %d device(s)", typed)
        except Exception:
            logger.exception("device classification failed")
            db.rollback()

        logger.info(
            "scan complete: seen=%d new=%d returned=%d offline=%d ip_changed=%d "
            "hostname_changed=%d vendor_mismatch=%d ip_conflicts=%d burst=%s omada_enriched=%d",
            len(results),
            len(summary.new_devices),
            len(summary.returned),
            len(summary.went_offline),
            len(summary.ip_changed),
            len(summary.hostname_changed),
            len(summary.vendor_mismatch),
            len(summary.ip_conflicts),
            summary.burst_anomaly,
            wifi_enriched,
        )

        if summary.suspicious_empty_scan:
            logger.warning(
                "scan saw 0 devices while devices were online -- treated as a scan problem, "
                "offline counters not advanced (check Settings -> Scanner interface/ranges)"
            )

        _send_notifications(db, summary)
    except Exception:
        logger.exception("scan cycle failed")
        db.rollback()
    finally:
        db.close()


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    logger.info("networkwatcher-scanner starting")
    names = NameEnricher()  # NetBIOS / mDNS lookups in the background
    names.start()
    while _running:
        cycle_start = time.monotonic()
        run_once()

        db = SessionLocal()
        try:
            interval = get_setting(db, "scanner", "scan_interval_seconds", 30)
        finally:
            db.close()

        elapsed = time.monotonic() - cycle_start
        sleep_for = max(0.0, interval - elapsed)
        for _ in range(int(sleep_for * 10)):
            if not _running:
                break
            time.sleep(0.1)

    names.stop()
    logger.info("networkwatcher-scanner stopped")


if __name__ == "__main__":
    main()
