# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org).

Versions before 1.0.0 were internal development milestones and were not tagged.

## [1.5.0] - 2026-11-19

### Added
- Settings → Backup: **device database export/import**. Export the device inventory (no events, statistics or ping results) as XLSX, CSV or PDF; import XLSX/CSV back in *merge* or *replace* mode. A preview shows new/updated/deleted devices and invalid rows before anything changes; imports that modify or delete existing data require typing `IMPORT` (enforced server-side).
- API: `GET /api/settings/devices-backup/export`, `POST /api/settings/devices-backup/preview`, `POST /api/settings/devices-backup/import`.

### Changed
- Telemetry: progress bars show their percentage inside the bar.
- Settings → Scanner: the network-scan / IP-conflict card always sits directly below the Scanner card (with its help card to the right), also on wide screens.

## [1.4.0] - 2026-11-19

### Added
- **Special devices** (Settings → Special): pick devices whose every online/offline change is notified on all configured channels (browser toast, MQTT `events/special`, webhook `SPECIAL_DEVICE`, e-mail), also when the device is trusted; optional "notify during quiet hours". A status card lists the special devices with their current state.
- API: `GET/PUT /api/settings/special`.

## [1.3.0] - 2026-11-19

### Added
- NetBIOS and mDNS names: queried in the background (unprivileged UDP, new/returned devices immediately, others every 6 h), shown as *NetBIOS* and *mDNS* columns (sortable, searchable), used to fill an empty hostname and as device-type hints.

## [1.2.0] - 2026-11-19

### Added
- Settings → Ping: reorder destinations by dragging the handle or with the up/down arrows (the order is also used on the Ping page) and edit address and name inline. Changing the address clears that destination's previous statistics.
- API: `PUT /api/ping/targets/order`; `PATCH /api/ping/targets/{id}` accepts `address`.

### Changed
- UI text uses plain hyphens instead of long dashes.

## [1.1.0] - 2026-11-19

### Added
- Device detail: **Prisutnost** (presence) section right under Uptime — online time, offline time and availability for today, and an online/offline step chart (today / 24 h / 7 days / 30 days) with the recorded state changes as points and a hover tooltip.
- Device detail: hover tooltip on the Uptime bar (state, from–to, duration).
- New endpoint `GET /api/devices/{id}/presence`.
- Ping → *Merači*: "Debljina" slider to make the rows compact so many targets fit on one screen.
- Dashboard: adjustable line thickness in the ⋮ menu of the series charts.

### Changed
- The Uptime bar now covers the whole history since the device was first seen (it used to be built from the last 100 events only, drawing everything older as online).
- Default chart line is thinner (1.5 px instead of 2 px).

## [1.0.1] - 2026-11-19

### Fixed
- False IP conflict when one device uses two MAC addresses (e.g. a phone with a private MAC on one SSID and its real MAC on another, which the DHCP server gives the same IP). MACs reporting the same DHCP hostname are now treated as one device, in both the ARP listener and the scanner.
- The date-time picker popup was covered by the next card when cards use the glass style (Network Time Machine, History, System logs).

### Added
- Full documentation in `docs/`: installation (Proxmox LXC, reverse proxy, backup, upgrade, uninstall), user guide, configuration reference, how detection works, integrations (MQTT/Home Assistant, webhook, e-mail, Omada), REST API, architecture and data model, operations & troubleshooting, development and release process.

## [1.0.0] - 2026-11-17

First public release.

### Added
- **Network scan detection**: new `networkwatcher-sniffer` service (passive, read-only ARP listener; the only service with `CAP_NET_RAW`). Reports hosts sweeping the subnet, with source, IP and number of probed addresses.
- **Known scanners**: per-device learned profile (6 h learning, persisted); only deviations are reported — higher scan rate, more targets than usual, or a new source IP (possible MAC spoofing).
- **IP conflict detection** that actually works: from ARP traffic (configurable window) and from scans (an IP flipping between two MACs); ongoing conflicts stay "active" on the dashboard until resolved.
- Automatic **device type** classification with icons; manual override of hostname and vendor (locked against automatic updates).
- TP-Link Omada: DHCP hostnames for wired and wireless clients, switch port of wired clients, access point names, presence of sleeping Wi-Fi clients, fingerprint-based vendor mismatch.
- Weekly refresh of the OUI vendor database (Wireshark/IEEE) with backfill; "private MAC" label for randomized addresses.
- **Notification log** for MQTT, webhook and SMTP (sent / failed / skipped with reason) and a UI view under *Sistem*.
- Dashboard: selectable time range for "online devices over time" (1 h – 60 days), readable axes, per-chart style and color/palette selection, detailed recent-events feed with its own period.
- Ping: RTT charts with ms/time axes, ranges 1 h – 10 days (server-side aggregation), robust scale for spikes; configurable ping-statistics retention.
- Serbian date/time picker; sorting on every table column; "reset filters" buttons; tooltip explaining trusted devices.
- Configurable minimum absence time before a device is marked OFFLINE.
- Application version shown in the UI and via `GET /api/version`; demo/mock server for screenshots.

### Changed
- Quiet hours are evaluated in a configurable time zone (default Europe/Belgrade) instead of the server's UTC clock.
- During quiet hours only push notifications are suppressed; per-device MQTT state topics keep updating so Home Assistant stays accurate.
- Trusted devices no longer send any routine notifications; security anomalies are still reported for them.
- Webhooks now also carry anomaly events (scan, IP conflict, vendor mismatch, burst of new devices).
- Pinger probes all targets in parallel so the configured interval is honored.
- "Online devices over time" collapses simultaneous transitions and down-samples long ranges.
- New-devices-per-day chart counts by local calendar day and shows days without new devices.
- Static files are served with `Cache-Control: no-cache`, so the UI updates right after a deploy.

### Fixed
- Non-ASCII characters (e.g. Serbian diacritics) were rejected because the database was created with `SQL_ASCII` encoding; installation now requires a UTF8 database.
- A failed or empty scan no longer marks every device offline.
- An unreachable MQTT broker can no longer stall the scan loop (connect back-off).
- The "Offline" device filter no longer lists devices that still carry the NEW badge.
- OUI vendor updates no longer raise false VENDOR_MISMATCH events.
- Manual device edits only log fields that actually changed.

## [0.3.0] - 2026-09-02

### Added
- Host telemetry page (CPU, per-core load, RAM, swap, disk, network I/O, process stats).
- Favicon and icons in the main navigation.
- Ping "meters" view next to the card view.

## [0.2.0] - 2026-09-01

### Added
- `networkwatcher-worker` service with configurable history retention and manual cleanup.
- Live health strip on the dashboard (scanner, database, MQTT, SMTP, webhook, Omada).
- PDF report options: period, trusted-device count, new-devices-per-day chart.
- Switchable chart styles (area / line / bars) on dashboard charts.

## [0.1.0] - 2026-08-31

### Added
- ARP/neighbor-table network scanner and detection engine (NEW / ONLINE / OFFLINE / RETURNED, debounce, burst detection).
- PostgreSQL models and Alembic migrations; MAC address as device identity, IP history.
- FastAPI REST API, WebSocket push and the web UI: dashboard, devices, event history, Network Time Machine, settings, system logs.
- MQTT with Home Assistant discovery, SMTP e-mail, generic webhooks, quiet hours, trusted devices.
- TP-Link Omada integration for Wi-Fi details.
- Ping monitoring service.
- Excel, CSV and PDF export; themes and custom background image.
- systemd units for deployment in a Proxmox LXC container.

[1.5.0]: https://github.com/zoomtronicOR/NDW---Network-device-watcher/releases/tag/v1.5.0
[1.4.0]: https://github.com/zoomtronicOR/NDW---Network-device-watcher/releases/tag/v1.4.0
[1.3.0]: https://github.com/zoomtronicOR/NDW---Network-device-watcher/releases/tag/v1.3.0
[1.2.0]: https://github.com/zoomtronicOR/NDW---Network-device-watcher/releases/tag/v1.2.0
[1.1.0]: https://github.com/zoomtronicOR/NDW---Network-device-watcher/releases/tag/v1.1.0
[1.0.1]: https://github.com/zoomtronicOR/NDW---Network-device-watcher/releases/tag/v1.0.1
[1.0.0]: https://github.com/zoomtronicOR/NDW---Network-device-watcher/releases/tag/v1.0.0
