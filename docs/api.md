# REST API

Base URL: `http://<host>:8080`. All endpoints are under `/api`, return JSON (except exports) and require no authentication — protect the service at the network level (see [installation](installation.md#10-optional-reverse-proxy-nginx-and-https)). Interactive OpenAPI documentation with request/response schemas is available at **`/docs`** (Swagger UI) and `/openapi.json`.

Timestamps are ISO 8601 in UTC. MAC addresses are upper-case with colons.

## System

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | `{"status": "ok", "version": "1.0.0"}` |
| GET | `/api/version` | `{"version": "1.0.0"}` |
| GET | `/api/stats` | Dashboard counters, component health (`scanner_status`, `database_status`, `mqtt_status`, `smtp_status`, `webhook_status`, `omada_status`, `sniffer_status`), `last_device`, `last_events`, `last_scan_at` |
| GET | `/api/telemetry` | Host CPU, load, memory, swap, disk, network I/O, process and system info |
| GET | `/api/logs` | Service logs from journald. Query: `source` (`all`, `web`, `scanner`, `pinger`, `worker`, `sniffer`), `level`, `search`, `since`, `until`, `page`, `page_size` (≤ 500), `sort` (`timestamp`, `level`, `source`, `message`), `order` |
| GET | `/api/logs/download` | Same filters, plain-text download |
| GET | `/api/notifications` | Notification log. Query: `channel` (`MQTT`, `WEBHOOK`, `SMTP`), `status` (`SUCCESS`, `FAILED`, `SKIPPED`), `event_type`, `search`, `page`, `page_size` (≤ 200), `sort` (`timestamp`, `channel`, `event_type`, `device`, `destination`, `status`, `error`), `order`. Response includes `summary` counts per status. |

## Devices

| Method | Path | Description |
|---|---|---|
| GET | `/api/devices` | List. Query: `search`, `status` (`NEW`, `ONLINE`, `OFFLINE` — mutually exclusive like the UI badges), `connection_type` (`LAN`, `WIFI`), `is_trusted`, `sort` (`status`, `device_type`, `mac_address`, `ip_address`, `hostname`, `vendor`, `connection_type`, `wifi_rssi`, `first_seen`, `last_seen`, `seen_count`, `custom_name`, `notes`, `wifi_ssid`, `interface`), `order` (`asc`/`desc`), `page`, `page_size` (≤ 200). Returns `{items, total}`. |
| GET | `/api/devices/{id}` | Detail with `ip_history` and the last 100 `events`. **Side effect:** acknowledges a NEW device (clears `is_new`). |
| PATCH | `/api/devices/{id}` | Update `custom_name`, `device_type`, `notes`, `is_trusted`, `hostname`, `vendor`. A non-empty `hostname`/`vendor` locks it against automatic updates; `null` unlocks and restores the automatic value. Setting `device_type` makes it user-owned; `null` hands it back to the classifier. Creates a `MANUAL_UPDATE` event listing changed fields. |
| GET | `/api/devices/{id}/presence?hours=24` | Online/offline timeline reconstructed from state events: `segments` `[{start, end, online}]`, `points` `[{timestamp, online, event_type}]` (recorded state changes plus `NOW`), and `today` `{since, online_seconds, offline_seconds}` counted from local midnight (time zone of the quiet-hours setting). `hours` 1–2160. |
| DELETE | `/api/devices/{id}` | Delete a device and its history. |

Device object (main fields): `id, mac_address, ip_address, hostname, dhcp_hostname, vendor, device_type, device_type_auto, connection_type, interface, wifi_ssid, wifi_rssi, switch_port, os_fingerprint, first_seen, last_seen, is_online, is_new, is_trusted, hostname_locked, vendor_locked, seen_count, custom_name, notes, status`.

## Events and history

| Method | Path | Description |
|---|---|---|
| GET | `/api/events` | Query: `device_id`, `event_type`, `search` (MAC, name, hostname, IP), `start`, `end`, `page`, `page_size` (≤ 200), `sort` (`timestamp`, `event_type`, `device`, `ip_address`, `details`, `vendor`), `order`. Items include `details` (JSON string) and device fields `device_mac`, `device_name`, `device_vendor`, `device_connection_type`, `device_type`, `device_is_trusted`. |
| GET | `/api/timemachine/bounds` | `{earliest, latest}` — available history range |
| GET | `/api/timemachine/state?at=<ISO time>` | Network state at a moment: `devices` (with `online`, IP at that time, `status_changed_at`), `online_count`, `offline_count`, `appeared_since`, `disappeared_since` (MAC lists, compared with now) |

Event types: `NEW_DEVICE`, `DEVICE_OFFLINE`, `DEVICE_RETURNED`, `IP_CHANGED`, `HOSTNAME_CHANGED`, `MANUAL_UPDATE`, `ANOMALY_BURST_NEW_DEVICES`, `VENDOR_MISMATCH`, `IP_CONFLICT`, `SCAN_DETECTED` (`DEVICE_ONLINE` is reserved).

## Charts

| Method | Path | Description |
|---|---|---|
| GET | `/api/charts/online-timeline?hours=24` | Online count over time (reconstructed from events), `{points: [{timestamp, online}], start, end}`. Long ranges are down-sampled to ≤ 600 points keeping minima and maxima. `hours` ≤ 2160. |
| GET | `/api/charts/new-devices-daily?days=30` | `{points: [{date, count}]}` per local calendar day, including zero days |
| GET | `/api/charts/connection-split` | `{items: [{label, count}]}` LAN / Wi-Fi |
| GET | `/api/charts/device-types` | by `device_type` |
| GET | `/api/charts/top-vendors?limit=8` | top vendors |

## Ping

| Method | Path | Description |
|---|---|---|
| GET | `/api/ping/targets` | List targets |
| POST | `/api/ping/targets` | `{"address": "8.8.8.8", "label": "Google DNS"}` |
| PATCH | `/api/ping/targets/{id}` | `{"address": …, "label": …, "enabled": true/false}`; a changed address deletes the target's previous results |
| PUT | `/api/ping/targets/order` | `{"ids": [3, 1, 2]}` sets the display order (`sort_order`); returns the ordered list |
| DELETE | `/api/ping/targets/{id}` | Delete target and its results |
| GET | `/api/ping/series?hours=24&buckets=200` | Per target: `target`, `latest` (raw last result) and `history` aggregated into ~`buckets` time buckets (`rtt_avg` of reachable samples, `rtt_min`, `rtt_max`, average `packet_loss_pct`, `samples`, `unreachable_samples`). Without `hours`: the last `limit` raw samples. |

## Settings

Each group has `GET` (current values, secrets reported only as `password_set` / `client_secret_set`) and `PUT` (partial update — send only the fields to change; send an empty password to clear it, omit it to keep it). Keys and defaults: [configuration reference](configuration.md).

| Path | Notes |
|---|---|
| `/api/settings/scanner` | Validates CIDRs |
| `/api/settings/scan-detection` | GET also returns `known_scanners` (learned profiles), `last_heartbeat_at`, `packets_seen`; MACs are normalized |
| `/api/settings/special` | `{macs, ignore_quiet_hours}`; GET also returns `devices` with current state |
| `/api/settings/history` | `retention_days`, `ping_retention_days` (`null` = unlimited) |
| `/api/settings/notifications` | Quiet hours and time zone (validated) |
| `/api/settings/mqtt` · `/smtp` · `/webhook` · `/omada` · `/ping` · `/appearance` | |

| Method | Path | Description |
|---|---|---|
| POST | `/api/settings/history/cleanup-now` | Run retention cleanup now; returns deleted counts |
| POST | `/api/test/mqtt` · `/api/test/smtp` · `/api/test/webhook` · `/api/test/omada` | `{"success": bool, "message": str}` |
| GET | `/api/settings/omada/sites` | Sites available on the controller |
| GET | `/api/settings/backup/export` | All settings as JSON (secrets stay encrypted) |
| POST | `/api/settings/backup/import` | Import that JSON |
| GET | `/api/settings/devices-backup/export?format=xlsx\|csv\|pdf` | Device inventory only (no events, statistics or ping results); XLSX/CSV use raw column names and can be re-imported, PDF is a read-only report |
| POST | `/api/settings/devices-backup/preview` | Multipart `file` (.xlsx/.csv) + `mode` (`merge`/`replace`); returns what the import would do (new/updated/unchanged/deleted devices, invalid rows) without changing anything |
| POST | `/api/settings/devices-backup/import` | Same fields + `confirm`; when the import updates or deletes existing data, `confirm` must be `IMPORT` or the request is rejected (400) |
| POST / DELETE | `/api/settings/appearance/background` | Upload (multipart `file`) / remove the background image |
| DELETE | `/api/settings/reset/devices` | Delete all devices and their history |

## Export

| Method | Path | Description |
|---|---|---|
| GET | `/api/export/excel` | `.xlsx` with all devices (formatted header, autofilter, frozen first row, date formats) |
| GET | `/api/export/csv` | Same columns as CSV |
| GET | `/api/export/pdf?days=30` | PDF report; `days` adds a period line and a new-devices-per-day chart |

## WebSocket

`GET /api/ws` (WebSocket). The server pushes JSON messages; clients send nothing.

```json
{"type": "scan_complete", "new_devices": [{"mac", "ip", "hostname", "vendor", "connection_type"}],
 "returned": [...], "went_offline": [...], "burst_anomaly": false}
```

```json
{"type": "anomaly", "anomaly": {"event_type": "SCAN_DETECTED", "mac": "…", "ip": "…", "name": "…",
 "vendor": "…", "target_count": 254, "window_seconds": 60, "reason": null}}
{"type": "anomaly", "anomaly": {"event_type": "IP_CONFLICT", "ip": "…", "macs": ["…", "…"]}}
```

`POST /api/internal/broadcast` is used by the scanner and sniffer processes to relay these messages to the web process; it only accepts requests from `127.0.0.1`.
