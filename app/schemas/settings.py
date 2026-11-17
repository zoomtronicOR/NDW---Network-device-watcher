from __future__ import annotations

from pydantic import BaseModel


class MqttSettingsOut(BaseModel):
    enabled: bool
    host: str | None
    port: int
    username: str | None
    password_set: bool
    tls_enabled: bool
    client_id: str
    base_topic: str
    qos: int
    retain: bool
    ha_discovery_enabled: bool
    ha_discovery_prefix: str


class MqttSettingsUpdate(BaseModel):
    enabled: bool | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    tls_enabled: bool | None = None
    client_id: str | None = None
    base_topic: str | None = None
    qos: int | None = None
    retain: bool | None = None
    ha_discovery_enabled: bool | None = None
    ha_discovery_prefix: str | None = None


class SmtpSettingsOut(BaseModel):
    enabled: bool
    host: str | None
    port: int
    username: str | None
    password_set: bool
    security: str
    from_address: str | None
    recipients: list[str]
    subject_prefix: str


class SmtpSettingsUpdate(BaseModel):
    enabled: bool | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    security: str | None = None
    from_address: str | None = None
    recipients: list[str] | None = None
    subject_prefix: str | None = None


class NotificationSettingsOut(BaseModel):
    quiet_hours_enabled: bool
    quiet_hours_start: str
    quiet_hours_end: str
    timezone: str


class NotificationSettingsUpdate(BaseModel):
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str | None = None


class ScannerSettingsOut(BaseModel):
    scan_interval_seconds: int
    network_ranges: list[str]
    interface: str | None
    settle_seconds: float
    resolve_hostnames: bool
    offline_threshold: int
    offline_grace_seconds: int


class ScannerSettingsUpdate(BaseModel):
    scan_interval_seconds: int | None = None
    network_ranges: list[str] | None = None
    interface: str | None = None
    settle_seconds: float | None = None
    resolve_hostnames: bool | None = None
    offline_threshold: int | None = None
    offline_grace_seconds: int | None = None


class ScanDetectionSettingsOut(BaseModel):
    enabled: bool
    threshold_hosts: int
    window_seconds: int
    ip_conflict_enabled: bool
    conflict_window_seconds: int
    cooldown_seconds: int
    ignore_macs: list[str]
    last_heartbeat_at: str | None
    packets_seen: int | None
    known_scanners: list[dict] = []


class ScanDetectionSettingsUpdate(BaseModel):
    enabled: bool | None = None
    threshold_hosts: int | None = None
    window_seconds: int | None = None
    ip_conflict_enabled: bool | None = None
    conflict_window_seconds: int | None = None
    cooldown_seconds: int | None = None
    ignore_macs: list[str] | None = None


class HistorySettingsOut(BaseModel):
    retention_days: int | None  # None = unlimited (§19.1)
    ping_retention_days: int | None  # None = unlimited


class HistorySettingsUpdate(BaseModel):
    retention_days: int | None = None
    ping_retention_days: int | None = None


class HistoryCleanupResult(BaseModel):
    device_events: int
    ip_history: int
    notification_log: int
    ping_results: int = 0


class WebhookSettingsOut(BaseModel):
    enabled: bool
    url: str | None
    headers: dict[str, str]


class WebhookSettingsUpdate(BaseModel):
    enabled: bool | None = None
    url: str | None = None
    headers: dict[str, str] | None = None


class OmadaSiteOut(BaseModel):
    site_id: str
    name: str


class OmadaSettingsOut(BaseModel):
    enabled: bool
    controller_url: str | None
    verify_ssl: bool
    omadac_id: str | None
    client_id: str | None
    client_secret_set: bool
    site_id: str | None
    site_name: str | None


class OmadaSettingsUpdate(BaseModel):
    enabled: bool | None = None
    controller_url: str | None = None
    verify_ssl: bool | None = None
    omadac_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    site_id: str | None = None
    site_name: str | None = None


class SettingRow(BaseModel):
    category: str
    key: str
    value: str | None = None
    is_secret: bool = False


class ConfigExportOut(BaseModel):
    exported_at: str
    settings: list[SettingRow]


class ConfigImportResult(BaseModel):
    imported: int


class AppearanceSettingsOut(BaseModel):
    theme: str
    primary_color: str
    secondary_color: str
    text_color: str
    card_style: str
    card_opacity: float
    border_radius: int
    card_blur: int
    background_enabled: bool
    background_image: str | None
    background_opacity: float
    background_blur: int
    background_brightness: int
    background_saturation: int
    overlay_opacity: float
    background_position: str
    background_size: str
    background_repeat: str


class AppearanceSettingsUpdate(BaseModel):
    theme: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    text_color: str | None = None
    card_style: str | None = None
    card_opacity: float | None = None
    border_radius: int | None = None
    card_blur: int | None = None
    background_enabled: bool | None = None
    background_opacity: float | None = None
    background_blur: int | None = None
    background_brightness: int | None = None
    background_saturation: int | None = None
    overlay_opacity: float | None = None
    background_position: str | None = None
    background_size: str | None = None
    background_repeat: str | None = None


class TestResult(BaseModel):
    success: bool
    message: str
