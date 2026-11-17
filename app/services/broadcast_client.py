from __future__ import annotations

import json
import logging
import urllib.request

logger = logging.getLogger("networkwatcher.broadcast")

_BROADCAST_URL = "http://127.0.0.1:8080/api/internal/broadcast"


def broadcast_scan_result(
    new_devices: list[dict], returned: list[dict], went_offline: list[dict], burst_anomaly: bool
) -> None:
    """Relay this scan's changes to the web process so it can push them to
    connected browsers over WebSocket (§41). The scanner and
    web API run as separate systemd services, so this local HTTP call is how
    they talk -- never raises, a down/restarting web service must not stop
    detection (§36).
    """
    if not (new_devices or returned or went_offline):
        return

    payload = json.dumps(
        {
            "type": "scan_complete",
            "new_devices": new_devices,
            "returned": returned,
            "went_offline": went_offline,
            "burst_anomaly": burst_anomaly,
        }
    ).encode("utf-8")
    req = urllib.request.Request(_BROADCAST_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        logger.warning("WebSocket broadcast failed (web service may be restarting)")


def broadcast_anomaly(anomaly: dict) -> None:
    """Push a single anomaly (SCAN_DETECTED / IP_CONFLICT from the ARP
    sniffer) to browsers as a toast. Never raises."""
    payload = json.dumps({"type": "anomaly", "anomaly": anomaly}).encode("utf-8")
    req = urllib.request.Request(_BROADCAST_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        logger.warning("WebSocket anomaly broadcast failed (web service may be restarting)")
