# Configuration reference

There are two kinds of configuration:

1. **`.env`** in the installation directory — only what is needed before the database is reachable.
2. **Everything else** is stored in the database table `settings` (category + key, JSON value) and edited in the web UI under *Podešavanja*. Services re-read their settings on every cycle, so changes apply without restarts.

## `.env`

| Variable | Description |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg2://networkwatcher:PASSWORD@localhost:5432/networkwatcher`. The database must be UTF8. |
| `SECRET_KEY` | Key used to encrypt stored secrets (SMTP/MQTT passwords, Omada client secret) with Fernet (SHA-256 of the key). Changing it makes existing secrets unreadable. |

## Scanner — category `scanner`

| Key | UI label | Default | Notes |
|---|---|---|---|
| `scan_interval_seconds` | Scan interval | 30 | Seconds between scans. 10–60 s is reasonable. |
| `network_ranges` | Mrežni opsezi | `["192.168.1.0/24"]` | List of CIDRs; every host address is probed each cycle. |
| `interface` | Interfejs | empty (automatic) | Restrict probing and neighbor reading to one interface, e.g. `eth0`. Also used by the ARP listener. |
| `settle_seconds` | Probe timeout | 1.5 | Wait after probing before reading the neighbor table. |
| `resolve_hostnames` | Razrešavaj hostname | true | Reverse DNS lookup (bounded by a short overall timeout). |
| `offline_threshold` | Offline threshold | 3 | Consecutive missed scans before a device can go OFFLINE. |
| `offline_grace_seconds` | Minimalna odsutnost pre OFFLINE | 300 | AND it must be unseen at least this long. Prevents false offline/returned pairs from devices in power-save mode. |

Fixed (not configurable): a **burst** of ≥ 5 new devices within 10 minutes raises one `ANOMALY_BURST_NEW_DEVICES` event.

## Network scan / IP conflict detection — category `scan_detection`

| Key | UI label | Default | Notes |
|---|---|---|---|
| `enabled` | Detekcija skeniranja mreže | true | |
| `threshold_hosts` | Prag: broj različitih adresa | 30 | Distinct target IPs one sender must ask for… |
| `window_seconds` | U vremenskom prozoru | 60 | …within this window to count as a scan. |
| `ip_conflict_enabled` | Detekcija IP konflikta | true | |
| `conflict_window_seconds` | Prozor za IP konflikt | 600 | Two MACs claiming the same IP within this window = conflict. |
| `cooldown_seconds` | Pauza između upozorenja | 600 | Minimum time between alerts for the same source / IP (also across restarts). |
| `ignore_macs` | Poznati skeneri | `[]` | Known scanners: their usual behavior is learned and only deviations are reported. See [detection](detection.md#known-scanners). |

Maintained automatically (read-only): `profiles` (learned behavior of known scanners), `last_heartbeat_at`, `packets_seen`.

## History — category `history`

| Key | UI label | Default | Notes |
|---|---|---|---|
| `retention_days` | Čuvanje istorije | 90 | Events, IP history and notification log older than this are deleted hourly. `null` = unlimited. Device records themselves are never deleted by retention. |
| `ping_retention_days` | Čuvanje ping statistike | 10 | Individual ping results. `null` = unlimited. The Ping page shows at most 10 days. |

## Ping — category `ping`

| Key | Default | Notes |
|---|---|---|
| `interval_seconds` | 30 | All enabled targets are pinged in parallel each cycle (3 echo requests, 2 s timeout each). |
| `color_bands` | ≤ 50 ms green, ≤ 150 ms yellow, ≤ 300 ms orange, above / unreachable red | List of `{max_ms, color}`; the last band has `max_ms: null`. |

Targets are stored in the `ping_targets` table (address or hostname, optional label, enabled flag).

## Notifications / quiet hours — category `notifications`

| Key | UI label | Default | Notes |
|---|---|---|---|
| `quiet_hours_enabled` | Tiha zona omogućena | false | |
| `quiet_hours_start` | Od | `23:00` | `HH:MM`. A window that crosses midnight is supported. |
| `quiet_hours_end` | Do | `07:00` | |
| `timezone` | Vremenska zona | `Europe/Belgrade` | IANA time zone in which start/end are interpreted (the server itself usually runs in UTC). |

During quiet hours: events are still recorded and shown in the UI; e-mails, MQTT **event** topics and webhooks are skipped (and logged as *skipped*). MQTT **state** topics keep updating.

## MQTT — category `mqtt`

| Key | Default | Notes |
|---|---|---|
| `enabled` | false | |
| `host`, `port` | –, 1883 | Broker address. |
| `username`, `password` | – | Password stored encrypted. |
| `tls_enabled` | false | Uses the system CA store. |
| `client_id` | `networkwatcher` | The ARP listener connects as `<client_id>-sniffer`. |
| `base_topic` | `networkwatcher` | Prefix of all topics. |
| `qos` | 0 | |
| `retain` | true | For state and stats topics (event topics are never retained). |
| `ha_discovery_enabled` | false | Publish Home Assistant discovery configs. |
| `ha_discovery_prefix` | `homeassistant` | |

## SMTP — category `smtp`

| Key | Default | Notes |
|---|---|---|
| `enabled` | false | |
| `host`, `port` | –, 587 | |
| `username`, `password` | – | Password stored encrypted. Gmail requires an App Password. |
| `security` | `STARTTLS` | `NONE`, `STARTTLS` or `SSL_TLS` (TLS from the first byte, usually port 465). |
| `from_address` | – | |
| `recipients` | `[]` | One e-mail per recipient. |
| `subject_prefix` | `[Network Watcher]` | |

## Special devices — category `special`

| Key | UI label | Default | Notes |
|---|---|---|---|
| `macs` | Special uređaji | `[]` | MACs notified on every online/offline change, on all channels, regardless of trusted status. |
| `ignore_quiet_hours` | Obaveštavaj i tokom tihe zone | false | |

## Webhook — category `webhook`

| Key | Default | Notes |
|---|---|---|
| `enabled` | false | |
| `url` | – | HTTP(S) endpoint; JSON is POSTed. |
| `headers` | `{}` | Extra headers, e.g. `Authorization: Bearer …` (one per line in the UI, `Name: value`). |

## Omada — category `omada`

| Key | Default | Notes |
|---|---|---|
| `enabled` | false | |
| `controller_url` | – | e.g. `https://192.168.1.10:8043` |
| `verify_ssl` | false | Controllers usually use a self-signed certificate. |
| `omadac_id`, `client_id`, `client_secret` | – | From the controller's Open API application (secret stored encrypted). |
| `site_id`, `site_name` | – | Chosen with *Učitaj lokacije*. Sync does nothing until a site is saved. |

## Appearance — category `appearance`

| Key | Default |
|---|---|
| `theme` | `dark` (`light`, `blue`, `green`, `purple`, `high_contrast`, `custom`) |
| `primary_color`, `secondary_color`, `text_color` | `#22D3EE`, `#818CF8`, `#E5E7EB` (used by the `custom` theme) |
| `card_style` | `transparent` (`solid`, `glass`) |
| `card_opacity`, `card_blur`, `border_radius` | 0.04, 12 px, 14 px |
| `background_enabled`, `background_image` | false, – |
| `background_opacity`, `background_blur` | 0.35, 4 px |
| `background_brightness`, `background_saturation` | 90 %, 100 % |
| `overlay_opacity` | 0.25 |
| `background_position`, `background_size`, `background_repeat` | `center`, `cover`, `no-repeat` |

Uploaded images (JPG/PNG/WEBP, max 8 MB, downscaled to 2560 px) are stored in `uploads/backgrounds/`.

## Per-browser preferences

Stored in the browser's `localStorage`, not in the database: chart style, colors and line thickness, dashboard ranges, Ping view, period and meter thickness, device-table visible columns and page size, device presence period, Sistem view.
