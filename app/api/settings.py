from __future__ import annotations

import ipaddress
import re
from datetime import datetime, timezone
from datetime import time as dt_time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.device import Device
from app.models.setting import Setting
from app.schemas.ping import ColorBand, PingSettingsOut, PingSettingsUpdate
from app.schemas.settings import (
    AppearanceSettingsOut,
    AppearanceSettingsUpdate,
    ConfigExportOut,
    ConfigImportResult,
    HistoryCleanupResult,
    HistorySettingsOut,
    HistorySettingsUpdate,
    MqttSettingsOut,
    MqttSettingsUpdate,
    NotificationSettingsOut,
    NotificationSettingsUpdate,
    OmadaSettingsOut,
    OmadaSettingsUpdate,
    OmadaSiteOut,
    ScanDetectionSettingsOut,
    ScanDetectionSettingsUpdate,
    ScannerSettingsOut,
    ScannerSettingsUpdate,
    SettingRow,
    SmtpSettingsOut,
    SmtpSettingsUpdate,
    TestResult,
    WebhookSettingsOut,
    WebhookSettingsUpdate,
)
from app.services.background_storage import InvalidImageError, delete_background, save_background
from app.services.crypto import encrypt
from app.services.mqtt_client import test_connection as test_mqtt_connection
from app.services.omada_client import list_sites_for_settings, test_connection as test_omada_connection
from app.services.retention import cleanup_history, cleanup_ping_results
from app.services.settings_store import get_setting, set_setting
from app.services.smtp_client import test_connection as test_smtp_connection
from app.services.webhook_client import test_connection as test_webhook_connection

router = APIRouter(tags=["settings"])

_MQTT_DEFAULTS = {
    "port": 1883,
    "tls_enabled": False,
    "client_id": "networkwatcher",
    "base_topic": "networkwatcher",
    "qos": 0,
    "retain": True,
    "ha_discovery_enabled": False,
    "ha_discovery_prefix": "homeassistant",
}

_SMTP_DEFAULTS = {
    "port": 587,
    "security": "STARTTLS",
    "recipients": [],
    "subject_prefix": "[Network Watcher]",
}

_NOTIFICATION_DEFAULTS = {
    "quiet_hours_enabled": False,
    "quiet_hours_start": "23:00",
    "quiet_hours_end": "07:00",
    "timezone": "Europe/Belgrade",
}

_SCANNER_DEFAULTS = {
    "scan_interval_seconds": 30,
    "network_ranges": ["192.168.1.0/24"],
    "interface": None,
    "settle_seconds": 1.5,
    "resolve_hostnames": True,
    "offline_threshold": 3,
    "offline_grace_seconds": 300,
}

_WEBHOOK_DEFAULTS = {"headers": {}}

_HISTORY_DEFAULTS = {"retention_days": 90, "ping_retention_days": 10}

_APPEARANCE_THEMES = {"dark", "light", "blue", "green", "purple", "high_contrast", "custom"}
_APPEARANCE_CARD_STYLES = {"solid", "transparent", "glass"}
_APPEARANCE_DEFAULTS = {
    "theme": "dark",
    "primary_color": "#22D3EE",
    "secondary_color": "#818CF8",
    "text_color": "#E5E7EB",
    "card_style": "transparent",
    "card_opacity": 0.04,
    "border_radius": 14,
    "card_blur": 12,
    # background_* defaults mirror §26's own example values
    "background_enabled": False,
    "background_image": None,
    "background_opacity": 0.35,
    "background_blur": 4,
    "background_brightness": 90,
    "background_saturation": 100,
    "overlay_opacity": 0.25,
    "background_position": "center",
    "background_size": "cover",
    "background_repeat": "no-repeat",
}


def _apply_settings_update(db: Session, category: str, payload: BaseModel) -> None:
    """Shared PUT logic: every field except `password` is written verbatim;
    `password` is only touched when the client explicitly sent it (and it is
    always encrypted before storage -- see §33).
    """
    changes = payload.model_dump(exclude_unset=True)
    password_provided = "password" in changes
    password_value = changes.pop("password", None)

    for key, value in changes.items():
        set_setting(db, category, key, value)

    if password_provided:
        if password_value:
            set_setting(db, category, "password", encrypt(password_value), is_secret=True)
        else:
            set_setting(db, category, "password", None, is_secret=True)


def _read_mqtt_settings(db: Session) -> MqttSettingsOut:
    return MqttSettingsOut(
        enabled=get_setting(db, "mqtt", "enabled", False),
        host=get_setting(db, "mqtt", "host", None),
        port=get_setting(db, "mqtt", "port", _MQTT_DEFAULTS["port"]),
        username=get_setting(db, "mqtt", "username", None),
        password_set=bool(get_setting(db, "mqtt", "password", None)),
        tls_enabled=get_setting(db, "mqtt", "tls_enabled", _MQTT_DEFAULTS["tls_enabled"]),
        client_id=get_setting(db, "mqtt", "client_id", _MQTT_DEFAULTS["client_id"]),
        base_topic=get_setting(db, "mqtt", "base_topic", _MQTT_DEFAULTS["base_topic"]),
        qos=get_setting(db, "mqtt", "qos", _MQTT_DEFAULTS["qos"]),
        retain=get_setting(db, "mqtt", "retain", _MQTT_DEFAULTS["retain"]),
        ha_discovery_enabled=get_setting(db, "mqtt", "ha_discovery_enabled", _MQTT_DEFAULTS["ha_discovery_enabled"]),
        ha_discovery_prefix=get_setting(db, "mqtt", "ha_discovery_prefix", _MQTT_DEFAULTS["ha_discovery_prefix"]),
    )


@router.get("/settings/mqtt", response_model=MqttSettingsOut)
def get_mqtt_settings(db: Session = Depends(get_db)) -> MqttSettingsOut:
    return _read_mqtt_settings(db)


@router.put("/settings/mqtt", response_model=MqttSettingsOut)
def update_mqtt_settings(payload: MqttSettingsUpdate, db: Session = Depends(get_db)) -> MqttSettingsOut:
    _apply_settings_update(db, "mqtt", payload)
    return _read_mqtt_settings(db)


@router.post("/test/mqtt", response_model=TestResult)
def test_mqtt() -> TestResult:
    ok, message = test_mqtt_connection()
    return TestResult(success=ok, message=message)


def _read_smtp_settings(db: Session) -> SmtpSettingsOut:
    return SmtpSettingsOut(
        enabled=get_setting(db, "smtp", "enabled", False),
        host=get_setting(db, "smtp", "host", None),
        port=get_setting(db, "smtp", "port", _SMTP_DEFAULTS["port"]),
        username=get_setting(db, "smtp", "username", None),
        password_set=bool(get_setting(db, "smtp", "password", None)),
        security=get_setting(db, "smtp", "security", _SMTP_DEFAULTS["security"]),
        from_address=get_setting(db, "smtp", "from_address", None),
        recipients=get_setting(db, "smtp", "recipients", _SMTP_DEFAULTS["recipients"]),
        subject_prefix=get_setting(db, "smtp", "subject_prefix", _SMTP_DEFAULTS["subject_prefix"]),
    )


@router.get("/settings/smtp", response_model=SmtpSettingsOut)
def get_smtp_settings(db: Session = Depends(get_db)) -> SmtpSettingsOut:
    return _read_smtp_settings(db)


@router.put("/settings/smtp", response_model=SmtpSettingsOut)
def update_smtp_settings(payload: SmtpSettingsUpdate, db: Session = Depends(get_db)) -> SmtpSettingsOut:
    _apply_settings_update(db, "smtp", payload)
    return _read_smtp_settings(db)


@router.post("/test/smtp", response_model=TestResult)
def test_smtp() -> TestResult:
    ok, message = test_smtp_connection()
    return TestResult(success=ok, message=message)


def _read_notification_settings(db: Session) -> NotificationSettingsOut:
    return NotificationSettingsOut(
        quiet_hours_enabled=get_setting(
            db, "notifications", "quiet_hours_enabled", _NOTIFICATION_DEFAULTS["quiet_hours_enabled"]
        ),
        quiet_hours_start=get_setting(
            db, "notifications", "quiet_hours_start", _NOTIFICATION_DEFAULTS["quiet_hours_start"]
        ),
        quiet_hours_end=get_setting(
            db, "notifications", "quiet_hours_end", _NOTIFICATION_DEFAULTS["quiet_hours_end"]
        ),
        timezone=get_setting(db, "notifications", "timezone", _NOTIFICATION_DEFAULTS["timezone"]),
    )


@router.get("/settings/notifications", response_model=NotificationSettingsOut)
def get_notification_settings(db: Session = Depends(get_db)) -> NotificationSettingsOut:
    return _read_notification_settings(db)


@router.put("/settings/notifications", response_model=NotificationSettingsOut)
def update_notification_settings(
    payload: NotificationSettingsUpdate, db: Session = Depends(get_db)
) -> NotificationSettingsOut:
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("timezone"):
        try:
            ZoneInfo(changes["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(status_code=400, detail=f"Nepoznata vremenska zona: {changes['timezone']}") from None
    for key in ("quiet_hours_start", "quiet_hours_end"):
        if changes.get(key):
            try:
                dt_time.fromisoformat(changes[key])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Neispravno vreme (format HH:MM): {changes[key]}") from None
    for key, value in changes.items():
        set_setting(db, "notifications", key, value)
    return _read_notification_settings(db)


def _read_scanner_settings(db: Session) -> ScannerSettingsOut:
    return ScannerSettingsOut(
        scan_interval_seconds=get_setting(
            db, "scanner", "scan_interval_seconds", _SCANNER_DEFAULTS["scan_interval_seconds"]
        ),
        network_ranges=get_setting(db, "scanner", "network_ranges", _SCANNER_DEFAULTS["network_ranges"]),
        interface=get_setting(db, "scanner", "interface", _SCANNER_DEFAULTS["interface"]),
        settle_seconds=get_setting(db, "scanner", "settle_seconds", _SCANNER_DEFAULTS["settle_seconds"]),
        resolve_hostnames=get_setting(db, "scanner", "resolve_hostnames", _SCANNER_DEFAULTS["resolve_hostnames"]),
        offline_threshold=get_setting(db, "scanner", "offline_threshold", _SCANNER_DEFAULTS["offline_threshold"]),
        offline_grace_seconds=get_setting(
            db, "scanner", "offline_grace_seconds", _SCANNER_DEFAULTS["offline_grace_seconds"]
        ),
    )


@router.get("/settings/scanner", response_model=ScannerSettingsOut)
def get_scanner_settings(db: Session = Depends(get_db)) -> ScannerSettingsOut:
    return _read_scanner_settings(db)


@router.put("/settings/scanner", response_model=ScannerSettingsOut)
def update_scanner_settings(payload: ScannerSettingsUpdate, db: Session = Depends(get_db)) -> ScannerSettingsOut:
    changes = payload.model_dump(exclude_unset=True)
    if "network_ranges" in changes:
        for cidr in changes["network_ranges"]:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Nevažeći mrežni opseg: {cidr}") from None

    for key, value in changes.items():
        set_setting(db, "scanner", key, value)
    return _read_scanner_settings(db)


def _read_history_settings(db: Session) -> HistorySettingsOut:
    return HistorySettingsOut(
        retention_days=get_setting(db, "history", "retention_days", _HISTORY_DEFAULTS["retention_days"]),
        ping_retention_days=get_setting(
            db, "history", "ping_retention_days", _HISTORY_DEFAULTS["ping_retention_days"]
        ),
    )


@router.get("/settings/history", response_model=HistorySettingsOut)
def get_history_settings(db: Session = Depends(get_db)) -> HistorySettingsOut:
    return _read_history_settings(db)


@router.put("/settings/history", response_model=HistorySettingsOut)
def update_history_settings(payload: HistorySettingsUpdate, db: Session = Depends(get_db)) -> HistorySettingsOut:
    for key, value in payload.model_dump(exclude_unset=True).items():
        set_setting(db, "history", key, value)
    return _read_history_settings(db)


@router.post("/settings/history/cleanup-now", response_model=HistoryCleanupResult)
def run_history_cleanup_now(db: Session = Depends(get_db)) -> HistoryCleanupResult:
    retention_days = get_setting(db, "history", "retention_days", _HISTORY_DEFAULTS["retention_days"])
    ping_days = get_setting(db, "history", "ping_retention_days", _HISTORY_DEFAULTS["ping_retention_days"])
    counts = cleanup_history(db, retention_days)
    counts["ping_results"] = cleanup_ping_results(db, ping_days)
    return HistoryCleanupResult(**counts)


_SCAN_DETECTION_DEFAULTS = {
    "enabled": True,
    "threshold_hosts": 30,
    "window_seconds": 60,
    "ip_conflict_enabled": True,
    "conflict_window_seconds": 600,
    "cooldown_seconds": 600,
    "ignore_macs": [],
}


def _read_scan_detection_settings(db: Session) -> ScanDetectionSettingsOut:
    def g(key):
        return get_setting(db, "scan_detection", key, _SCAN_DETECTION_DEFAULTS[key])

    profiles = get_setting(db, "scan_detection", "profiles", {}) or {}
    learning_seconds = 6 * 3600
    now_ts = datetime.now(timezone.utc).timestamp()
    known = []
    for mac in g("ignore_macs") or []:
        device = db.execute(select(Device).where(Device.mac_address == mac)).scalar_one_or_none()
        entry = {
            "mac": mac,
            "name": (device.custom_name or device.hostname) if device else None,
            "ip": device.ip_address if device else None,
            "observed": False,
        }
        data = profiles.get(mac)
        if data:
            from app.services.arp_monitor import ScannerProfile

            summary = ScannerProfile.from_dict(data).summary(now_ts, learning_seconds)
            summary["learning_until"] = datetime.fromtimestamp(summary["learning_until"], timezone.utc).isoformat()
            entry.update(summary, observed=True)
        known.append(entry)

    return ScanDetectionSettingsOut(
        known_scanners=known,
        enabled=g("enabled"),
        threshold_hosts=g("threshold_hosts"),
        window_seconds=g("window_seconds"),
        ip_conflict_enabled=g("ip_conflict_enabled"),
        conflict_window_seconds=g("conflict_window_seconds"),
        cooldown_seconds=g("cooldown_seconds"),
        ignore_macs=g("ignore_macs"),
        last_heartbeat_at=get_setting(db, "scan_detection", "last_heartbeat_at", None),
        packets_seen=get_setting(db, "scan_detection", "packets_seen", None),
    )


@router.get("/settings/scan-detection", response_model=ScanDetectionSettingsOut)
def get_scan_detection_settings(db: Session = Depends(get_db)) -> ScanDetectionSettingsOut:
    return _read_scan_detection_settings(db)


@router.put("/settings/scan-detection", response_model=ScanDetectionSettingsOut)
def update_scan_detection_settings(
    payload: ScanDetectionSettingsUpdate, db: Session = Depends(get_db)
) -> ScanDetectionSettingsOut:
    changes = payload.model_dump(exclude_unset=True)
    if "ignore_macs" in changes:
        cleaned = []
        for mac in changes["ignore_macs"] or []:
            hex_only = re.sub(r"[^0-9A-Fa-f]", "", mac)
            if len(hex_only) != 12:
                raise HTTPException(status_code=400, detail=f"Neispravna MAC adresa: {mac}")
            cleaned.append(":".join(hex_only[i : i + 2] for i in range(0, 12, 2)).upper())
        changes["ignore_macs"] = sorted(set(cleaned))
    for key in ("threshold_hosts", "window_seconds", "cooldown_seconds", "conflict_window_seconds"):
        if key in changes and (changes[key] is None or changes[key] < 1):
            raise HTTPException(status_code=400, detail=f"Vrednost mora biti pozitivna: {key}")
    for key, value in changes.items():
        set_setting(db, "scan_detection", key, value)
    return _read_scan_detection_settings(db)


def _read_special_settings(db: Session) -> dict:
    macs = [m.upper() for m in (get_setting(db, "special", "macs", []) or [])]
    by_mac = {d.mac_address: d for d in db.execute(select(Device).where(Device.mac_address.in_(macs))).scalars()} if macs else {}
    devices = []
    for mac in macs:
        d = by_mac.get(mac)
        devices.append(
            {
                "mac": mac,
                "id": d.id if d else None,
                "name": (d.custom_name or d.hostname) if d else None,
                "ip": d.ip_address if d else None,
                "device_type": d.device_type if d else None,
                "is_online": d.is_online if d else None,
                "last_seen": d.last_seen.isoformat() if d and d.last_seen else None,
            }
        )
    return {
        "macs": macs,
        "ignore_quiet_hours": bool(get_setting(db, "special", "ignore_quiet_hours", False)),
        "devices": devices,
    }


@router.get("/settings/special")
def get_special_settings(db: Session = Depends(get_db)) -> dict:
    return _read_special_settings(db)


@router.put("/settings/special")
def update_special_settings(payload: dict, db: Session = Depends(get_db)) -> dict:
    if "macs" in payload:
        cleaned = []
        for mac in payload["macs"] or []:
            hex_only = re.sub(r"[^0-9A-Fa-f]", "", str(mac))
            if len(hex_only) != 12:
                raise HTTPException(status_code=400, detail=f"Neispravna MAC adresa: {mac}")
            norm = ":".join(hex_only[i : i + 2] for i in range(0, 12, 2)).upper()
            if norm not in cleaned:
                cleaned.append(norm)
        set_setting(db, "special", "macs", cleaned)
    if "ignore_quiet_hours" in payload:
        set_setting(db, "special", "ignore_quiet_hours", bool(payload["ignore_quiet_hours"]))
    return _read_special_settings(db)


def _read_webhook_settings(db: Session) -> WebhookSettingsOut:
    return WebhookSettingsOut(
        enabled=get_setting(db, "webhook", "enabled", False),
        url=get_setting(db, "webhook", "url", None),
        headers=get_setting(db, "webhook", "headers", _WEBHOOK_DEFAULTS["headers"]),
    )


@router.get("/settings/webhook", response_model=WebhookSettingsOut)
def get_webhook_settings(db: Session = Depends(get_db)) -> WebhookSettingsOut:
    return _read_webhook_settings(db)


@router.put("/settings/webhook", response_model=WebhookSettingsOut)
def update_webhook_settings(payload: WebhookSettingsUpdate, db: Session = Depends(get_db)) -> WebhookSettingsOut:
    for key, value in payload.model_dump(exclude_unset=True).items():
        set_setting(db, "webhook", key, value)
    return _read_webhook_settings(db)


@router.post("/test/webhook", response_model=TestResult)
def test_webhook() -> TestResult:
    ok, message = test_webhook_connection()
    return TestResult(success=ok, message=message)


def _read_omada_settings(db: Session) -> OmadaSettingsOut:
    return OmadaSettingsOut(
        enabled=get_setting(db, "omada", "enabled", False),
        controller_url=get_setting(db, "omada", "controller_url", None),
        verify_ssl=get_setting(db, "omada", "verify_ssl", False),
        omadac_id=get_setting(db, "omada", "omadac_id", None),
        client_id=get_setting(db, "omada", "client_id", None),
        client_secret_set=bool(get_setting(db, "omada", "client_secret", None)),
        site_id=get_setting(db, "omada", "site_id", None),
        site_name=get_setting(db, "omada", "site_name", None),
    )


@router.get("/settings/omada", response_model=OmadaSettingsOut)
def get_omada_settings(db: Session = Depends(get_db)) -> OmadaSettingsOut:
    return _read_omada_settings(db)


@router.put("/settings/omada", response_model=OmadaSettingsOut)
def update_omada_settings(payload: OmadaSettingsUpdate, db: Session = Depends(get_db)) -> OmadaSettingsOut:
    changes = payload.model_dump(exclude_unset=True)
    secret_provided = "client_secret" in changes
    secret_value = changes.pop("client_secret", None)

    for key, value in changes.items():
        set_setting(db, "omada", key, value)

    if secret_provided:
        if secret_value:
            set_setting(db, "omada", "client_secret", encrypt(secret_value), is_secret=True)
        else:
            set_setting(db, "omada", "client_secret", None, is_secret=True)

    return _read_omada_settings(db)


@router.post("/test/omada", response_model=TestResult)
def test_omada() -> TestResult:
    ok, message = test_omada_connection()
    return TestResult(success=ok, message=message)


@router.get("/settings/omada/sites", response_model=list[OmadaSiteOut])
def get_omada_sites() -> list[OmadaSiteOut]:
    ok, message, sites = list_sites_for_settings()
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return [OmadaSiteOut(**s) for s in sites]


@router.get("/settings/backup/export", response_model=ConfigExportOut)
def export_config(db: Session = Depends(get_db)) -> ConfigExportOut:
    rows = db.execute(select(Setting)).scalars().all()
    return ConfigExportOut(
        exported_at=datetime.now(timezone.utc).isoformat(),
        settings=[
            SettingRow(category=r.category, key=r.key, value=r.value, is_secret=r.is_secret) for r in rows
        ],
    )


@router.post("/settings/backup/import", response_model=ConfigImportResult)
def import_config(payload: ConfigExportOut, db: Session = Depends(get_db)) -> ConfigImportResult:
    count = 0
    for row in payload.settings:
        existing = db.execute(
            select(Setting).where(Setting.category == row.category, Setting.key == row.key)
        ).scalar_one_or_none()
        if existing:
            existing.value = row.value
            existing.is_secret = row.is_secret
        else:
            db.add(Setting(category=row.category, key=row.key, value=row.value, is_secret=row.is_secret))
        count += 1
    db.commit()
    return ConfigImportResult(imported=count)


def _read_appearance_settings(db: Session) -> AppearanceSettingsOut:
    return AppearanceSettingsOut(
        theme=get_setting(db, "appearance", "theme", _APPEARANCE_DEFAULTS["theme"]),
        primary_color=get_setting(db, "appearance", "primary_color", _APPEARANCE_DEFAULTS["primary_color"]),
        secondary_color=get_setting(db, "appearance", "secondary_color", _APPEARANCE_DEFAULTS["secondary_color"]),
        text_color=get_setting(db, "appearance", "text_color", _APPEARANCE_DEFAULTS["text_color"]),
        card_style=get_setting(db, "appearance", "card_style", _APPEARANCE_DEFAULTS["card_style"]),
        card_opacity=get_setting(db, "appearance", "card_opacity", _APPEARANCE_DEFAULTS["card_opacity"]),
        border_radius=get_setting(db, "appearance", "border_radius", _APPEARANCE_DEFAULTS["border_radius"]),
        card_blur=get_setting(db, "appearance", "card_blur", _APPEARANCE_DEFAULTS["card_blur"]),
        background_enabled=get_setting(
            db, "appearance", "background_enabled", _APPEARANCE_DEFAULTS["background_enabled"]
        ),
        background_image=get_setting(db, "appearance", "background_image", _APPEARANCE_DEFAULTS["background_image"]),
        background_opacity=get_setting(
            db, "appearance", "background_opacity", _APPEARANCE_DEFAULTS["background_opacity"]
        ),
        background_blur=get_setting(db, "appearance", "background_blur", _APPEARANCE_DEFAULTS["background_blur"]),
        background_brightness=get_setting(
            db, "appearance", "background_brightness", _APPEARANCE_DEFAULTS["background_brightness"]
        ),
        background_saturation=get_setting(
            db, "appearance", "background_saturation", _APPEARANCE_DEFAULTS["background_saturation"]
        ),
        overlay_opacity=get_setting(db, "appearance", "overlay_opacity", _APPEARANCE_DEFAULTS["overlay_opacity"]),
        background_position=get_setting(
            db, "appearance", "background_position", _APPEARANCE_DEFAULTS["background_position"]
        ),
        background_size=get_setting(db, "appearance", "background_size", _APPEARANCE_DEFAULTS["background_size"]),
        background_repeat=get_setting(
            db, "appearance", "background_repeat", _APPEARANCE_DEFAULTS["background_repeat"]
        ),
    )


@router.get("/settings/appearance", response_model=AppearanceSettingsOut)
def get_appearance_settings(db: Session = Depends(get_db)) -> AppearanceSettingsOut:
    return _read_appearance_settings(db)


@router.put("/settings/appearance", response_model=AppearanceSettingsOut)
def update_appearance_settings(
    payload: AppearanceSettingsUpdate, db: Session = Depends(get_db)
) -> AppearanceSettingsOut:
    changes = payload.model_dump(exclude_unset=True)
    if "theme" in changes and changes["theme"] not in _APPEARANCE_THEMES:
        raise HTTPException(status_code=400, detail=f"Nepoznata tema: {changes['theme']}")
    if "card_style" in changes and changes["card_style"] not in _APPEARANCE_CARD_STYLES:
        raise HTTPException(status_code=400, detail=f"Nepoznat stil kartice: {changes['card_style']}")

    for key, value in changes.items():
        set_setting(db, "appearance", key, value)
    return _read_appearance_settings(db)


@router.post("/settings/appearance/background", response_model=AppearanceSettingsOut)
async def upload_background(file: UploadFile = File(...), db: Session = Depends(get_db)) -> AppearanceSettingsOut:
    raw = await file.read()
    try:
        url = save_background(raw)
    except InvalidImageError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    delete_background(get_setting(db, "appearance", "background_image", None))
    set_setting(db, "appearance", "background_image", url)
    set_setting(db, "appearance", "background_enabled", True)
    return _read_appearance_settings(db)


@router.delete("/settings/appearance/background", response_model=AppearanceSettingsOut)
def remove_background(db: Session = Depends(get_db)) -> AppearanceSettingsOut:
    delete_background(get_setting(db, "appearance", "background_image", None))
    set_setting(db, "appearance", "background_image", None)
    set_setting(db, "appearance", "background_enabled", False)
    return _read_appearance_settings(db)


class ResetResult(BaseModel):
    deleted: int


@router.delete("/settings/reset/devices", response_model=ResetResult)
def reset_devices(db: Session = Depends(get_db)) -> ResetResult:
    """Wipe every device (and, via ON DELETE CASCADE, its device_events/ip_history) --
    e.g. when moving the container to a different network/Proxmox host and starting
    a fresh inventory. App settings (MQTT/SMTP/scanner/...) are left untouched.
    """
    count = db.execute(select(func.count()).select_from(Device)).scalar_one()
    db.execute(delete(Device))
    db.commit()
    return ResetResult(deleted=count)


_PING_DEFAULT_BANDS = [
    {"max_ms": 50, "color": "#34D399"},
    {"max_ms": 150, "color": "#FBBF24"},
    {"max_ms": 300, "color": "#FB923C"},
    {"max_ms": None, "color": "#F87171"},
]
_PING_DEFAULTS = {"interval_seconds": 30, "color_bands": _PING_DEFAULT_BANDS}


def _read_ping_settings(db: Session) -> PingSettingsOut:
    return PingSettingsOut(
        interval_seconds=get_setting(db, "ping", "interval_seconds", _PING_DEFAULTS["interval_seconds"]),
        color_bands=get_setting(db, "ping", "color_bands", _PING_DEFAULTS["color_bands"]),
    )


@router.get("/settings/ping", response_model=PingSettingsOut)
def get_ping_settings(db: Session = Depends(get_db)) -> PingSettingsOut:
    return _read_ping_settings(db)


@router.put("/settings/ping", response_model=PingSettingsOut)
def update_ping_settings(payload: PingSettingsUpdate, db: Session = Depends(get_db)) -> PingSettingsOut:
    changes = payload.model_dump(exclude_unset=True)
    if "color_bands" in changes:
        changes["color_bands"] = [ColorBand(**b).model_dump() for b in changes["color_bands"]]
    for key, value in changes.items():
        set_setting(db, "ping", key, value)
    return _read_ping_settings(db)
