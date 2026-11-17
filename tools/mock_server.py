"""Demo/mock server for README screenshots.

Serves the real frontend (app/static) together with a fake, fully synthetic
REST API: fictional device names, a 192.168.1.0/24 network, random MAC
addresses. No database, no network scanning, standard library only.

    python tools/mock_server.py            # http://127.0.0.1:8765
    python tools/mock_server.py --port 9000

Then take screenshots of /, /devices.html, /ping.html, /events.html,
/settings.html (e.g. with a headless browser).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "app" / "version.py").read_text()).group(1)

rnd = random.Random(42)
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def rand_mac(private: bool = False) -> str:
    first = rnd.randrange(0, 256) & 0xFC
    if private:
        first |= 0x02
    return ":".join(f"{b:02X}" for b in [first] + [rnd.randrange(0, 256) for _ in range(5)])


# (custom_name, device_type, vendor, connection, hostname, private_mac)
CATALOG = [
    ("Router", "Router", "Routerboard.com", "LAN", "router", False),
    ("Access point - hodnik", "Access point", "TP-LINK TECHNOLOGIES CO.,LTD.", "LAN", "ap-hodnik", False),
    ("Access point - dnevna soba", "Access point", "TP-LINK TECHNOLOGIES CO.,LTD.", "LAN", "ap-dnevna", False),
    ("Switch - kancelarija", "Switch", "TP-LINK TECHNOLOGIES CO.,LTD.", "LAN", None, False),
    ("Proxmox host", "Server", "Dell Inc.", "LAN", "pve", False),
    ("Home Assistant", "Server", "Proxmox Server Solutions GmbH", "LAN", "homeassistant", False),
    ("NAS", "NAS", "Synology Incorporated", "LAN", "diskstation", False),
    ("Desktop PC", "Computer", "Giga-Byte Technology Co.,Ltd.", "LAN", "desktop-k7d2", False),
    ("Laptop - posao", "Laptop", "Intel Corporate", "WIFI", "laptop-posao", False),
    ("Telefon - Ana", "Telefon", None, "WIFI", "android-a1", True),
    ("Telefon - Marko", "Telefon", None, "WIFI", "iphone-marko", True),
    ("Tablet - deca", "Tablet", "Samsung Electronics Co.,Ltd", "WIFI", "galaxy-tab", False),
    ("TV dnevna soba", "TV", "LG Electronics", "LAN", "lgwebostv", False),
    ("TV Box spavaća soba", "TV Box", "Xiaomi Communications Co Ltd", "WIFI", "mibox", False),
    ("Kamera - dvorište", "Camera", "Hangzhou Hikvision Digital Technology Co.,Ltd.", "LAN", None, False),
    ("Kamera - ulaz", "Camera", "Hangzhou Hikvision Digital Technology Co.,Ltd.", "WIFI", None, False),
    ("Štampač", "Štampač", "Brother Industries, LTD.", "WIFI", "brn3c2af4", False),
    ("Robot usisivač", "IOT", "Beijing Roborock Technology Co., Ltd.", "WIFI", "roborock-s7", False),
    ("Pametni zvučnik", "IOT", "Google, Inc.", "WIFI", "google-home-mini", False),
    ("Termostat", "IOT", "Espressif Inc.", "WIFI", "esp32-termostat", False),
    ("LED traka kuhinja", "IOT", "Espressif Inc.", "WIFI", "wled-kuhinja", False),
    ("Sat - Ana", "Smart Watch", None, "WIFI", None, True),
    ("Konzola", "Konzola", "Sony Interactive Entertainment Inc.", "LAN", "ps5", False),
]
for i in range(1, 7):
    CATALOG.append((f"Pametna utičnica {i}", "IOT", "Tuya Smart Inc.", "WIFI", None, False))
for i in range(1, 5):
    CATALOG.append((f"Senzor temperature {i}", "IOT", "Espressif Inc.", "WIFI", f"esp-senzor-{i}", False))
for i in range(1, 4):
    CATALOG.append((f"Sijalica {i}", "IOT", "Signify Netherlands B.V.", "WIFI", None, False))
# a few never-named / brand new ones
CATALOG += [
    (None, None, "Espressif Inc.", "WIFI", "esp_3f21a0", False),
    (None, "IOT", "Tuya Smart Inc.", "WIFI", "wlan0", False),
    (None, None, None, "WIFI", None, True),
    (None, "Computer", "ASUSTek COMPUTER INC.", "LAN", "desktop-gost", False),
]

SSIDS = ["Kuca", "Kuca-5G"]
APS = ["hodnik", "dnevna soba"]

DEVICES: list[dict] = []
for idx, (name, dtype, vendor, conn, host, private) in enumerate(CATALOG, start=1):
    first_seen = NOW - timedelta(days=rnd.randint(20, 80), minutes=rnd.randint(0, 1400))
    is_new = name is None and idx >= len(CATALOG) - 2
    if is_new:
        first_seen = NOW - timedelta(hours=rnd.randint(1, 20))
    online = rnd.random() > 0.17 or name in ("Router", "Proxmox host", "NAS", "Home Assistant")
    last_seen = NOW - timedelta(seconds=rnd.randint(2, 25)) if online else NOW - timedelta(hours=rnd.randint(2, 70))
    ip = "192.168.1.1" if name == "Router" else f"192.168.1.{10 + idx * 3}"
    DEVICES.append(
        {
            "id": idx,
            "mac_address": rand_mac(private),
            "ip_address": ip,
            "ipv6_address": None,
            "hostname": host,
            "dhcp_hostname": host if conn == "WIFI" else None,
            "mdns_hostname": None,
            "netbios_hostname": None,
            "vendor": vendor,
            "device_type": dtype,
            "device_type_auto": bool(dtype) and name is None,
            "connection_type": conn,
            "interface": f"{rnd.choice(APS).title()}" if conn == "WIFI" else "eth0",
            "wifi_ssid": rnd.choice(SSIDS) if conn == "WIFI" else None,
            "wifi_rssi": -rnd.randint(32, 78) if conn == "WIFI" else None,
            "gateway": None,
            "vlan": None,
            "switch_port": f"Switch - kancelarija / port {rnd.randint(1, 8)}" if conn == "LAN" and rnd.random() < 0.4 else None,
            "os_fingerprint": None,
            "first_seen": iso(first_seen),
            "last_seen": iso(last_seen),
            "is_online": online,
            "is_new": is_new,
            "is_trusted": name is not None and rnd.random() < 0.55,
            "hostname_locked": False,
            "vendor_locked": False,
            "seen_count": rnd.randint(200, 9000),
            "custom_name": name,
            "notes": "Rezervisana DHCP adresa" if name in ("NAS", "Proxmox host") else None,
            "status": "NEW" if is_new else ("ONLINE" if online else "OFFLINE"),
        }
    )
BY_ID = {d["id"]: d for d in DEVICES}

# ---------------- events ----------------
EVENTS: list[dict] = []
eid = 0


def add_event(dev: dict, etype: str, ts: datetime, details: dict | None = None) -> None:
    global eid
    eid += 1
    EVENTS.append(
        {
            "id": eid,
            "device_id": dev["id"],
            "event_type": etype,
            "ip_address": dev["ip_address"],
            "timestamp": iso(ts),
            "details": json.dumps(details) if details else None,
            "device_mac": dev["mac_address"],
            "device_name": dev["custom_name"] or dev["hostname"],
            "device_vendor": dev["vendor"],
            "device_connection_type": dev["connection_type"],
            "device_type": dev["device_type"],
            "device_is_trusted": dev["is_trusted"],
        }
    )


roamers = [d for d in DEVICES if d["device_type"] in ("Telefon", "Tablet", "Laptop", "Smart Watch")]
for d in roamers:
    t = NOW - timedelta(days=7)
    while True:
        t += timedelta(hours=rnd.uniform(3, 11))
        if t >= NOW - timedelta(minutes=20):
            break
        add_event(d, "DEVICE_OFFLINE", t)
        t += timedelta(hours=rnd.uniform(0.5, 6))
        if t >= NOW - timedelta(minutes=10):
            break
        add_event(d, "DEVICE_RETURNED", t)
for d in DEVICES:
    if d["is_new"]:
        add_event(d, "NEW_DEVICE", datetime.fromisoformat(d["first_seen"]))
gost = DEVICES[-1]
add_event(gost, "SCAN_DETECTED", NOW - timedelta(minutes=37),
          {"source_mac": gost["mac_address"], "source_ip": gost["ip_address"], "target_count": 254, "window_seconds": 60, "method": "ARP sweep"})
lap = BY_ID[9]
add_event(lap, "IP_CHANGED", NOW - timedelta(hours=5), {"old_ip": "192.168.1.143", "new_ip": lap["ip_address"]})
add_event(BY_ID[20], "HOSTNAME_CHANGED", NOW - timedelta(hours=9), {"old_hostname": "esp32-a1b2", "new_hostname": "esp32-termostat"})
EVENTS.sort(key=lambda e: e["timestamp"], reverse=True)

# ---------------- ping ----------------
PING_TARGETS = [
    (1, "192.168.1.1", "Router", 0.4, 0.15, 0.0),
    (2, "8.8.8.8", "Google DNS", 12.0, 3.0, 0.002),
    (3, "1.1.1.1", "Cloudflare", 10.5, 2.5, 0.002),
    (4, "192.168.1.31", "NAS", 0.5, 0.2, 0.0),
    (5, "192.168.1.55", "Kamera - dvorište", 3.0, 2.5, 0.02),
    (6, "192.168.1.13", "Access point - hodnik", 0.7, 0.3, 0.0),
]


def ping_series(hours: float) -> list[dict]:
    out = []
    buckets = 200
    step = hours * 3600 / buckets
    for tid, addr, label, base, jitter, loss_rate in PING_TARGETS:
        r = random.Random(tid * 1000 + int(hours))
        hist = []
        for i in range(buckets):
            ts = NOW - timedelta(seconds=step * (buckets - i))
            down = loss_rate and r.random() < loss_rate
            spike = r.random() < 0.03
            avg = max(0.1, base + r.gauss(0, jitter) + (base * r.uniform(3, 8) if spike else 0))
            hist.append(
                {
                    "timestamp": iso(ts),
                    "reachable": not down,
                    "packet_loss_pct": 100.0 if down else (33.3 if r.random() < 0.01 else 0.0),
                    "rtt_min": None if down else round(avg * 0.8, 3),
                    "rtt_avg": None if down else round(avg, 3),
                    "rtt_max": None if down else round(avg * 1.4, 3),
                    "rtt_mdev": None,
                    "samples": max(1, int(step / 5)),
                    "unreachable_samples": 1 if down else 0,
                }
            )
        latest = dict(hist[-1], timestamp=iso(NOW - timedelta(seconds=2)), reachable=True, packet_loss_pct=0.0)
        if latest["rtt_avg"] is None:
            latest.update(rtt_avg=base, rtt_min=base * 0.8, rtt_max=base * 1.3)
        out.append(
            {
                "target": {"id": tid, "address": addr, "label": label, "enabled": True, "created_at": iso(NOW - timedelta(days=30))},
                "latest": latest,
                "history": hist,
            }
        )
    return out


# ---------------- charts ----------------
def online_timeline(hours: float) -> dict:
    start = NOW - timedelta(hours=hours)
    points = []
    current = sum(1 for d in DEVICES if d["is_online"])
    n = 160
    for i in range(n + 1):
        ts = start + (NOW - start) * (i / n)
        local_hour = (ts.hour + 1) % 24
        day_dip = 6 * math.exp(-((local_hour - 13) ** 2) / 18)  # phones away during the day
        value = round(current + 4 - day_dip + rnd.choice([-1, 0, 0, 0, 1]))
        points.append({"timestamp": iso(ts), "online": value})
    points[-1]["online"] = current
    return {"points": points, "start": iso(start), "end": iso(NOW)}


def new_devices_daily(days: int) -> dict:
    today = NOW.date()
    pts = []
    for i in range(days):
        day = today - timedelta(days=days - 1 - i)
        pts.append({"date": str(day), "count": rnd.choice([0, 0, 0, 0, 1, 1, 2]) if i != days - 1 else 2})
    return {"points": pts}


def split(field: str, default: str) -> dict:
    counts: dict[str, int] = {}
    for d in DEVICES:
        k = d[field] or default
        counts[k] = counts.get(k, 0) + 1
    return {"items": [{"label": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]}


def stats() -> dict:
    online = [d for d in DEVICES if d["is_online"]]
    return {
        "total_devices": len(DEVICES),
        "online": len(online),
        "offline": len(DEVICES) - len(online),
        "new_devices": sum(d["is_new"] for d in DEVICES),
        "wifi_devices": sum(d["connection_type"] == "WIFI" for d in DEVICES),
        "lan_devices": sum(d["connection_type"] == "LAN" for d in DEVICES),
        "active_ip_conflicts": 0,
        "active_scans_detected": 1,
        "sniffer_status": "ONLINE",
        "last_device": max(DEVICES, key=lambda d: d["first_seen"]),
        "last_events": EVENTS[:10],
        "last_scan_at": iso(NOW - timedelta(seconds=4)),
        "scanner_status": "ONLINE",
        "database_status": "ONLINE",
        "mqtt_status": "ONLINE",
        "smtp_status": "CONFIGURED",
        "webhook_status": "DISABLED",
        "omada_status": "ONLINE",
    }


def list_devices(q: dict) -> dict:
    items = list(DEVICES)
    status = q.get("status")
    if status == "NEW":
        items = [d for d in items if d["is_new"]]
    elif status == "ONLINE":
        items = [d for d in items if d["is_online"] and not d["is_new"]]
    elif status == "OFFLINE":
        items = [d for d in items if not d["is_online"] and not d["is_new"]]
    if q.get("connection_type"):
        items = [d for d in items if d["connection_type"] == q["connection_type"]]
    if q.get("is_trusted") == "true":
        items = [d for d in items if d["is_trusted"]]
    if q.get("search"):
        s = q["search"].lower()
        items = [d for d in items if any(s in str(d.get(k) or "").lower() for k in ("mac_address", "ip_address", "hostname", "vendor", "custom_name"))]
    key = q.get("sort", "last_seen")
    desc = q.get("order", "desc") == "desc"

    def sort_key(d):
        v = d.get(key)
        if key == "ip_address" and v:
            return tuple(int(x) for x in v.split("."))
        return (v is None, v if v is not None else "")

    items.sort(key=sort_key, reverse=desc)
    page, size = int(q.get("page", 1)), int(q.get("page_size", 25))
    return {"items": items[(page - 1) * size: page * size], "total": len(items)}


def list_events(q: dict) -> dict:
    items = list(EVENTS)
    if q.get("event_type"):
        items = [e for e in items if e["event_type"] == q["event_type"]]
    if q.get("start"):
        items = [e for e in items if e["timestamp"] >= q["start"].replace("Z", "+00:00")]
    page, size = int(q.get("page", 1)), int(q.get("page_size", 50))
    return {"items": items[(page - 1) * size: page * size], "total": len(items)}


def device_detail(dev_id: int) -> dict:
    d = dict(BY_ID[dev_id])
    d["ip_history"] = [{"ip_address": d["ip_address"], "first_seen": d["first_seen"], "last_seen": d["last_seen"]}]
    d["events"] = [e for e in EVENTS if e["device_id"] == dev_id][:30]
    return d


APPEARANCE = {
    "theme": "dark", "primary_color": "#22D3EE", "secondary_color": "#818CF8", "text_color": "#E5E7EB",
    "card_style": "transparent", "card_opacity": 0.04, "border_radius": 14, "card_blur": 12,
    "background_enabled": False, "background_image": None, "background_opacity": 0.35, "background_blur": 4,
    "background_brightness": 90, "background_saturation": 100, "overlay_opacity": 0.25,
    "background_position": "center", "background_size": "cover", "background_repeat": "no-repeat",
}

SETTINGS = {
    "/api/settings/scanner": {"scan_interval_seconds": 30, "network_ranges": ["192.168.1.0/24"], "interface": "eth0",
                              "settle_seconds": 1.5, "resolve_hostnames": True, "offline_threshold": 3, "offline_grace_seconds": 300},
    "/api/settings/history": {"retention_days": 90, "ping_retention_days": 10},
    "/api/settings/notifications": {"quiet_hours_enabled": True, "quiet_hours_start": "23:00", "quiet_hours_end": "07:00", "timezone": "Europe/Belgrade"},
    "/api/settings/mqtt": {"enabled": True, "host": "192.168.1.50", "port": 1883, "username": "mqtt", "password_set": True, "tls_enabled": False,
                           "client_id": "networkwatcher", "base_topic": "networkwatcher", "qos": 0, "retain": True,
                           "ha_discovery_enabled": True, "ha_discovery_prefix": "homeassistant"},
    "/api/settings/smtp": {"enabled": True, "host": "smtp.example.com", "port": 587, "username": "alerts@example.com", "password_set": True,
                           "security": "STARTTLS", "from_address": "alerts@example.com", "recipients": ["admin@example.com"], "subject_prefix": "[Network Watcher]"},
    "/api/settings/webhook": {"enabled": False, "url": None, "headers": {}},
    "/api/settings/omada": {"enabled": True, "controller_url": "https://192.168.1.10:8043", "verify_ssl": False, "omadac_id": "demo",
                            "client_id": "demo", "client_secret_set": True, "site_id": "site1", "site_name": "Kuca"},
    "/api/settings/ping": {"interval_seconds": 5, "color_bands": [
        {"max_ms": 50, "color": "#34d399"}, {"max_ms": 150, "color": "#fbbf24"}, {"max_ms": 300, "color": "#fb923c"}, {"max_ms": None, "color": "#f87171"}]},
    "/api/settings/appearance": APPEARANCE,
}


def scan_detection() -> dict:
    return {
        "enabled": True, "threshold_hosts": 30, "window_seconds": 60, "ip_conflict_enabled": True,
        "conflict_window_seconds": 600, "cooldown_seconds": 600, "ignore_macs": [BY_ID[6]["mac_address"]],
        "last_heartbeat_at": iso(NOW - timedelta(seconds=12)), "packets_seen": 48213,
        "known_scanners": [{
            "mac": BY_ID[6]["mac_address"], "name": "Home Assistant", "ip": BY_ID[6]["ip_address"], "observed": True,
            "learning": False, "learning_until": iso(NOW - timedelta(days=3)), "requests_per_hour": 1480,
            "typical_targets": 41, "max_targets": 44, "hours_observed": 24, "ips": [BY_ID[6]["ip_address"]],
        }],
    }


def notifications() -> dict:
    items = []
    for i, e in enumerate(EVENTS[:25]):
        trusted = e["device_is_trusted"]
        items.append({
            "id": i + 1, "timestamp": e["timestamp"], "channel": "MQTT", "event_type": e["event_type"],
            "device_id": e["device_id"], "device_mac": e["device_mac"], "device_name": e["device_name"],
            "destination": f"networkwatcher/events/{e['event_type'].lower()}",
            "status": "SKIPPED" if trusted and e["event_type"] != "SCAN_DETECTED" else "SUCCESS",
            "error": "poverljiv uređaj" if trusted and e["event_type"] != "SCAN_DETECTED" else None,
        })
    return {"total": len(items), "summary": {"SUCCESS": sum(i["status"] == "SUCCESS" for i in items), "SKIPPED": sum(i["status"] == "SKIPPED" for i in items)}, "items": items}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):  # quiet
        pass

    def _json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if not path.startswith("/api/"):
            return super().do_GET()

        routes = {
            "/api/version": lambda: {"version": VERSION},
            "/api/stats": stats,
            "/api/charts/online-timeline": lambda: online_timeline(float(q.get("hours", 24))),
            "/api/charts/new-devices-daily": lambda: new_devices_daily(int(q.get("days", 30))),
            "/api/charts/connection-split": lambda: split("connection_type", "Nepoznato"),
            "/api/charts/device-types": lambda: split("device_type", "Nepoznato"),
            "/api/charts/top-vendors": lambda: {"items": [i for i in split("vendor", "")["items"] if i["label"]][: int(q.get("limit", 8))]},
            "/api/devices": lambda: list_devices(q),
            "/api/events": lambda: list_events(q),
            "/api/ping/series": lambda: ping_series(float(q.get("hours", 1))),
            "/api/ping/targets": lambda: [s["target"] for s in ping_series(1)],
            "/api/settings/scan-detection": scan_detection,
            "/api/notifications": notifications,
            "/api/logs": lambda: {"total": 0, "items": []},
        }
        m = re.fullmatch(r"/api/devices/(\d+)", path)
        if m and int(m.group(1)) in BY_ID:
            return self._json(device_detail(int(m.group(1))))
        if path in routes:
            return self._json(routes[path]())
        if path in SETTINGS:
            return self._json(SETTINGS[path])
        return self._json({"detail": "not available in demo"}, 404)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    print(f"Network Device Watcher demo v{VERSION}: http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
