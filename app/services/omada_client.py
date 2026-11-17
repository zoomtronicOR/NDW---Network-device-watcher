from __future__ import annotations

import json
import logging
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from app.database import SessionLocal
from app.services.crypto import decrypt
from app.services.settings_store import get_setting, set_setting

logger = logging.getLogger("networkwatcher.omada")

# Cached access token, since it's valid ~2h (§2.3.1 of the controller's own
# Open API Access Guide) and re-authenticating every scan cycle would be wasteful
# and risks the API rate limit (§1.1, status 429).
_token_cache: dict[str, object] = {"token": None, "expires_at": 0.0}


def _normalize_mac(mac: str) -> str:
    hex_only = re.sub(r"[^0-9A-Fa-f]", "", mac)
    return ":".join(hex_only[i : i + 2] for i in range(0, len(hex_only), 2)).upper()


def _ssl_context(verify_ssl: bool) -> ssl.SSLContext:
    if verify_ssl:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _call(method: str, url: str, verify_ssl: bool, body: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"AccessToken={token}")
    ctx = _ssl_context(verify_ssl)
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("errorCode") not in (0, None):
        raise RuntimeError(payload.get("msg") or f"Omada API greška {payload.get('errorCode')}")
    return payload


def _load_config(db) -> dict | None:
    if not get_setting(db, "omada", "enabled", False):
        return None
    controller_url = get_setting(db, "omada", "controller_url", None)
    omadac_id = get_setting(db, "omada", "omadac_id", None)
    client_id = get_setting(db, "omada", "client_id", None)
    secret_enc = get_setting(db, "omada", "client_secret", None)
    if not controller_url or not omadac_id or not client_id or not secret_enc:
        return None
    return {
        "base_url": controller_url.rstrip("/"),
        "verify_ssl": get_setting(db, "omada", "verify_ssl", False),
        "omadac_id": omadac_id,
        "client_id": client_id,
        "client_secret": decrypt(secret_enc),
        "site_id": get_setting(db, "omada", "site_id", None),
    }


def _get_access_token(config: dict, force: bool = False) -> str:
    now = time.monotonic()
    if not force and _token_cache["token"] and now < float(_token_cache["expires_at"]):
        return str(_token_cache["token"])

    url = f"{config['base_url']}/openapi/authorize/token?grant_type=client_credentials"
    body = {
        "omadacId": config["omadac_id"],
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
    }
    payload = _call("POST", url, config["verify_ssl"], body=body)
    result = payload["result"]
    token = result["accessToken"]
    expires_in = result.get("expiresIn", 7200)
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + max(60, expires_in - 60)
    return token


def list_sites(config: dict) -> list[dict]:
    token = _get_access_token(config)
    url = f"{config['base_url']}/openapi/v1/{config['omadac_id']}/sites?pageSize=100&page=1"
    payload = _call("GET", url, config["verify_ssl"], token=token)
    return [{"site_id": s["siteId"], "name": s["name"]} for s in payload["result"]["data"]]


def list_clients(config: dict) -> list[dict]:
    """All currently connected clients -- wireless (SSID/RSSI/AP, §47)
    and wired ones behind Omada switches (switch name + port). Both carry the
    DHCP hostname the controller observed (`hostName`)."""
    token = _get_access_token(config)
    url = f"{config['base_url']}/openapi/v2/{config['omadac_id']}/sites/{config['site_id']}/clients"
    body = {"page": 1, "pageSize": 1000}
    payload = _call("POST", url, config["verify_ssl"], body=body, token=token)
    return payload["result"]["data"]


def list_wireless_clients(config: dict) -> list[dict]:
    return [c for c in list_clients(config) if c.get("wireless")]


def list_infra_devices(config: dict) -> list[dict]:
    """The controller's own managed devices (APs, switches, gateways)."""
    token = _get_access_token(config)
    url = f"{config['base_url']}/openapi/v1/{config['omadac_id']}/sites/{config['site_id']}/devices?page=1&pageSize=200"
    result = _call("GET", url, config["verify_ssl"], token=token)["result"]
    return result["data"] if isinstance(result, dict) else (result or [])


def test_connection() -> tuple[bool, str]:
    db = SessionLocal()
    try:
        config = _load_config(db)
    finally:
        db.close()
    if config is None:
        return False, "Omada podešavanja nisu kompletna (URL, Omada ID, Client ID i Client Secret su obavezni)"

    try:
        _get_access_token(config, force=True)
        sites = list_sites(config)
    except Exception as e:
        return False, str(e)

    if not sites:
        return True, "Konekcija uspešna, ali kontroler nema nijednu lokaciju (site)"
    names = ", ".join(s["name"] for s in sites)
    return True, f"Konekcija uspešna. Lokacije: {names}"


def list_sites_for_settings() -> tuple[bool, str, list[dict]]:
    db = SessionLocal()
    try:
        config = _load_config(db)
    finally:
        db.close()
    if config is None:
        return False, "Omada podešavanja nisu kompletna", []
    try:
        sites = list_sites(config)
    except Exception as e:
        return False, str(e), []
    return True, "OK", sites


def is_configured(db) -> bool:
    config = _load_config(db)
    return bool(config and config.get("site_id"))


_INFRA_CACHE_SECONDS = 600
_infra_cache: dict[str, object] = {"at": 0.0, "data": {}}
_MAC_LIKE = re.compile(r"^[0-9A-Fa-f]{2}([-:][0-9A-Fa-f]{2}){5}$")
_TRAILING_MAC = re.compile(r"\s*-?\s*[0-9A-Fa-f]{2}(-[0-9A-Fa-f]{2}){5}\s*$")


def fetch_clients(db) -> dict[str, dict] | None:
    """Currently connected Omada clients (wireless + wired), keyed by
    normalized MAC. None when the integration is off/unconfigured or the
    controller is unreachable -- callers must treat None as "no
    information", never as "no clients" (§36). Never raises."""
    config = _load_config(db)
    if config is None or not config.get("site_id"):
        return None

    try:
        clients = list_clients(config)
    except Exception as e:
        # A cached token can be revoked/expired early on the controller side;
        # retry once with a fresh one before giving up for this cycle.
        try:
            _get_access_token(config, force=True)
            clients = list_clients(config)
        except Exception:
            logger.warning("Omada sync failed: %s", e)
            return None

    # Dashboard health strip freshness check (§35).
    set_setting(db, "omada", "last_sync_at", datetime.now(timezone.utc).isoformat())
    return {_normalize_mac(c["mac"]): c for c in clients if c.get("mac") and c.get("active", True) is not False}


def fetch_infra_devices(db) -> dict[str, dict]:
    """Omada APs/switches/gateways keyed by MAC, cached 10 min. {} on any problem."""
    now = time.monotonic()
    if now - float(_infra_cache["at"]) < _INFRA_CACHE_SECONDS:
        return _infra_cache["data"]  # type: ignore[return-value]
    config = _load_config(db)
    if config is None or not config.get("site_id"):
        return {}
    try:
        devices = list_infra_devices(config)
    except Exception as e:
        logger.warning("Omada device list failed: %s", e)
        return _infra_cache["data"]  # type: ignore[return-value]
    data = {
        _normalize_mac(d["mac"]): {"type": d.get("type"), "name": d.get("name"), "model": d.get("model")}
        for d in devices
        if d.get("mac")
    }
    _infra_cache.update(at=now, data=data)
    return data


def _client_hostname(client: dict) -> str | None:
    host = (client.get("hostName") or "").strip()
    if host and not _MAC_LIKE.match(host):
        return host
    # `name` is the Omada alias; it defaults to the MAC when nobody named it.
    name = (client.get("name") or "").strip()
    if name and not _MAC_LIKE.match(name):
        return name
    return None


def _fingerprint(client: dict) -> tuple[str | None, str | None]:
    """(vendor, full fingerprint) from Omada's DHCP/traffic fingerprinting."""
    vendor = (client.get("vendor") or "").strip()
    os_name = (client.get("osName") or "").strip()
    vendor = None if vendor.lower() in ("", "unknown") else vendor
    os_name = None if os_name.lower() in ("", "unknown") else os_name
    parts = [p for p in (vendor, os_name) if p]
    return vendor, (" / ".join(parts) if parts else None)


def _set_hostname(device, new_host: str, now: datetime, events: list) -> None:
    """Omada-sourced hostname: only fills an empty hostname or replaces a
    previous Omada-sourced one -- never a reverse-DNS or manually locked name."""
    from app.models.device_event import DeviceEvent
    from app.models.enums import EventType

    old_dhcp = device.dhcp_hostname
    device.dhcp_hostname = new_host
    if device.hostname_locked or device.hostname == new_host:
        return
    if device.hostname is None or device.hostname == old_dhcp:
        if device.hostname:
            events.append(
                DeviceEvent(
                    device_id=device.id,
                    event_type=EventType.HOSTNAME_CHANGED.value,
                    ip_address=device.ip_address,
                    timestamp=now,
                    details=json.dumps({"old_hostname": device.hostname, "new_hostname": new_host, "source": "Omada"}),
                )
            )
        device.hostname = new_host


def apply_omada_clients(
    db,
    by_mac: dict[str, dict],
    scanned_macs: set[str],
    infra: dict[str, dict] | None = None,
    vendor_mismatch_out: list[str] | None = None,
) -> int:
    """Enrich devices from the controller (only after a *successful* fetch):

    * Wi-Fi clients: connection WIFI, SSID, RSSI, AP name.
    * Wired clients behind Omada switches: LAN + "switch / port N".
    * ARP-seen devices the controller doesn't know: LAN.
    * DHCP hostname (`hostName`) -> dhcp_hostname, and hostname when empty.
    * Omada infra devices (APs/switches): their controller name as hostname.
    * Omada's vendor/OS fingerprint -> os_fingerprint; a changed fingerprint
      vendor for the same MAC raises VENDOR_MISMATCH (§8.1, possible
      MAC spoofing). The OUI vendor can't do this -- it's a pure function of
      the MAC itself.
    """
    from sqlalchemy import select

    from app.models.device import Device
    from app.models.device_event import DeviceEvent
    from app.models.enums import ConnectionType, EventType

    infra = infra or {}
    now = datetime.now(timezone.utc)
    macs = set(by_mac) | set(scanned_macs) | set(infra)
    if not macs:
        return 0
    devices = db.execute(select(Device).where(Device.mac_address.in_(macs))).scalars().all()
    events: list = []
    updated = 0
    for device in devices:
        infra_dev = infra.get(device.mac_address)
        if infra_dev:
            name = _TRAILING_MAC.sub("", infra_dev.get("name") or "").strip()
            if name and not device.hostname and not device.hostname_locked:
                device.hostname = name
            device.connection_type = ConnectionType.LAN.value

        client = by_mac.get(device.mac_address)
        if not client:
            if device.mac_address in scanned_macs and not infra_dev and device.connection_type != ConnectionType.LAN.value:
                device.connection_type = ConnectionType.LAN.value
                device.wifi_ssid = None
                device.wifi_rssi = None
            continue

        if client.get("wireless"):
            device.connection_type = ConnectionType.WIFI.value
            device.wifi_ssid = client.get("ssid") or device.wifi_ssid
            if client.get("rssi") is not None:
                device.wifi_rssi = client["rssi"]
            if client.get("apName"):
                device.interface = _TRAILING_MAC.sub("", client["apName"]).strip() or client["apName"]
            device.switch_port = None
        else:
            device.connection_type = ConnectionType.LAN.value
            device.wifi_ssid = None
            device.wifi_rssi = None
            if client.get("switchName"):
                switch = _TRAILING_MAC.sub("", client["switchName"]).strip() or client["switchName"]
                device.switch_port = f"{switch} / port {client['port']}" if client.get("port") else switch

        host = _client_hostname(client)
        if host:
            _set_hostname(device, host, now, events)

        fp_vendor, fp = _fingerprint(client)
        if fp:
            old_fp = device.os_fingerprint
            old_vendor = old_fp.split(" / ")[0] if old_fp else None
            if old_vendor and fp_vendor and old_vendor.lower() != fp_vendor.lower():
                events.append(
                    DeviceEvent(
                        device_id=device.id,
                        event_type=EventType.VENDOR_MISMATCH.value,
                        ip_address=device.ip_address,
                        timestamp=now,
                        details=json.dumps(
                            {"old_vendor": old_fp, "new_vendor": fp, "source": "Omada fingerprint"}
                        ),
                    )
                )
                if vendor_mismatch_out is not None:
                    vendor_mismatch_out.append(device.mac_address)
            device.os_fingerprint = fp
        updated += 1

    for event in events:
        db.add(event)
    db.commit()
    return updated
