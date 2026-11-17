# Architecture

## Processes

NDW is five small Python processes sharing one PostgreSQL database. Each is a systemd unit; a failure or restart of one never stops the others.

```text
                   ┌──────────────────────── LAN segment ─────────────────────────┐
                   │                                                              │
   UDP probe + ip neigh │                   ARP frames (read-only)   ICMP echo     │
                   ▼                                  ▼                  ▼          │
        ┌────────────────────┐            ┌────────────────────┐ ┌──────────────┐  │
        │ scanner            │            │ sniffer            │ │ pinger       │  │
        │ detection engine   │            │ scan / IP-conflict │ │ ping targets │  │
        │ Omada sync         │            │ known-scanner      │ └──────┬───────┘  │
        │ type classifier    │            │ profiles           │        │          │
        │ MQTT/SMTP/webhook  │            │ MQTT/webhook       │        │          │
        └───┬───────────┬────┘            └──────┬────────┬────┘        │          │
            │           │ HTTP 127.0.0.1         │        │             │          │
            │           └──────────┐  ┌──────────┘        │             │          │
            ▼                      ▼  ▼                   ▼             ▼          │
        ┌───────────────────────────────────────────────────────────────────┐     │
        │                           PostgreSQL                              │     │
        └───────────────────────────────▲───────────────────────────────────┘     │
                                        │                                         │
        ┌────────────────────┐   ┌──────┴─────────────┐                           │
        │ worker             │   │ web (uvicorn)      │◄── browsers (HTTP + WS) ──┘
        │ retention cleanup  │   │ REST API, WebSocket│
        │ vendor DB refresh  │   │ static web UI      │
        └────────────────────┘   └────────────────────┘
```

| Process | Entry point | Loop | Privileges |
|---|---|---|---|
| web | `uvicorn app.main:app` | request driven | none |
| scanner | `app/scanner_main.py` | every `scan_interval_seconds` | none |
| sniffer | `app/sniffer_main.py` | blocking read on an AF_PACKET socket, settings reload every 30 s | `CAP_NET_RAW` (systemd `AmbientCapabilities`, bounded to that capability, `NoNewPrivileges`) |
| pinger | `app/pinger_main.py` | every `ping.interval_seconds` | none; uses `/usr/bin/ping` which has a file capability |
| worker | `app/worker_main.py` | hourly | none |

**Cross-process communication.** The scanner and the sniffer push real-time changes to browsers by POSTing to `http://127.0.0.1:8080/api/internal/broadcast`; the web process forwards them to all WebSocket clients. Everything else goes through the database. Settings are read from the database on every cycle, so the UI changes behavior without restarts.

**Failure isolation.** MQTT, SMTP, webhook and Omada calls are wrapped so that errors are logged and never propagate into detection. The MQTT client reconnects with a 60-second back-off. The scanner skips a cycle when the neighbor table cannot be read.

## Scan cycle (scanner)

1. Probe all addresses in the configured ranges, read `ip neigh` → list of (MAC, IP, hostname, interface).
2. Fetch Omada clients (if configured) — used as an additional presence signal.
3. `DetectionEngine.process_scan()` — upsert devices, IP history, NEW / RETURNED / IP_CHANGED / HOSTNAME_CHANGED events, IP-conflict check, offline debounce, burst check. One transaction.
4. Apply Omada enrichment (Wi-Fi details, switch port, hostnames, fingerprint).
5. Auto-classify device types.
6. Notifications (MQTT events + state, webhook, e-mail) and the WebSocket broadcast.

## Data model

| Table | Purpose | Key columns |
|---|---|---|
| `devices` | One row per MAC — permanent inventory, never touched by retention | `mac_address` (unique), `ip_address`, `hostname`, `dhcp_hostname`, `vendor`, `device_type`, `device_type_auto`, `connection_type`, `interface`, `wifi_ssid`, `wifi_rssi`, `switch_port`, `os_fingerprint`, `first_seen`, `last_seen`, `is_online`, `is_new`, `is_trusted`, `hostname_locked`, `vendor_locked`, `seen_count`, `consecutive_misses`, `custom_name`, `notes`; reserved: `ipv6_address`, `mdns_hostname`, `netbios_hostname`, `gateway`, `vlan` |
| `device_events` | Event history (source for charts, Time Machine, uptime bars) | `device_id`, `event_type`, `ip_address`, `timestamp`, `details` (JSON text) |
| `ip_history` | Every IP a device used | `device_id`, `ip_address`, `first_seen`, `last_seen` |
| `settings` | All user configuration | `category`, `key` (unique together), `value` (JSON text), `is_secret`, `updated_at` |
| `notification_log` | Every notification attempt | `device_id`, `notification_type` (MQTT/WEBHOOK/SMTP), `event_type`, `destination`, `status`, `error`, `timestamp` |
| `ping_targets` | Ping monitoring targets | `address`, `label`, `enabled` |
| `ping_results` | Raw ping samples (index on `target_id, timestamp`) | `target_id`, `timestamp`, `reachable`, `packet_loss_pct`, `rtt_min/avg/max/mdev` |

`device_events`, `ip_history` and `ping_results` cascade on delete of their parent. Event and connection types are stored as plain strings (not database enums) so new types need no schema change. There is no snapshot table: the online-over-time chart and the Network Time Machine replay `device_events`.

Schema changes are Alembic migrations in `migrations/versions/`; run `alembic upgrade head` after every upgrade.

## Frontend

Plain HTML/CSS/JavaScript served as static files by the web process — no framework, no build step.

| File | Role |
|---|---|
| `app/static/*.html` | One page per main tab |
| `js/common.js` | Shared helpers: formatting, event descriptions, toasts, device-type icons, sortable tables, Serbian date-time picker, per-browser preferences, version badge |
| `js/api.js` | Thin REST client |
| `js/charts.js` | SVG charts (series, donut, bar list, ping chart) with axes, tooltips and theming |
| `js/ws-client.js` | WebSocket client with reconnect; shows toasts and triggers page refreshes |
| `js/theme.js` | Applies the appearance settings (loaded in `<head>` to avoid a flash) |
| `js/<page>.js` | Page logic |
| `css/style.css` | All styles, themed through CSS custom properties |

Static responses carry `Cache-Control: no-cache`, so browsers revalidate (cheap 304) and always run the current version after an upgrade.

## Security model

- No user accounts by design; access control belongs to the network (LAN/VLAN, firewall, VPN) or a reverse proxy.
- Least privilege: only the sniffer has `CAP_NET_RAW`, and only to read ARP; ping uses a capability on the `ping` binary, not on Python.
- Secrets in the database are encrypted with a key derived from `SECRET_KEY` and never returned by the API.
- The internal broadcast endpoint accepts requests only from localhost.
- Webhook URLs are logged without their query string.
