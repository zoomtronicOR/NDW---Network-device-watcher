# User guide

The web interface is in Serbian. This guide quotes labels exactly as they appear (in *italics*) with an English explanation. The main navigation has eight tabs: **Dashboard, Uređaji (Devices), Ping, Istorija (History), Network Time Machine, Podešavanja (Settings), Sistem (System), Telemetrija (Telemetry)**. The current version is shown next to the title.

All pages refresh automatically. New devices, scans and IP conflicts also arrive instantly over WebSocket as pop-up notifications (toasts) with a short beep (browsers may mute it until you have clicked somewhere on the page).

## Device status

| Badge | Meaning |
|---|---|
| **NOV** (new) | Seen for the first time and not yet acknowledged. Opening the device's detail panel acknowledges it. |
| **ONLINE** | Currently present on the network. |
| **OFFLINE** | Missing for several consecutive scans *and* for at least the minimum absence time (default 5 min). |
| **VRAĆEN** (returned) | Shown in the event history when an offline device comes back. |

A ★ next to the status marks a **trusted** (*poverljiv*) device — see [trusted devices](#trusted-devices).

## Dashboard

- **Status strip** — health of each component: *Scanner*, *Baza podataka* (database), *MQTT*, *SMTP*, *Webhook*, *Omada*, *ARP sniffer* and the time of the last scan. Green = working / configured, red = not responding, grey = not configured. SMTP and webhook show *Podešeno* (configured) because they only connect when there is something to send.
- **Stat cards** — total, online, offline, new, Wi-Fi and LAN devices, *Aktivni IP konflikti* (IP addresses used by two MACs in the last 15 minutes) and *Skeniranja mreže (24h)* (network scans in the last 24 hours). The last two cards are links to the filtered event history.
- **Online uređaji kroz vreme** (online devices over time) — choose the range with the chips 1h, 6h, 12h, 24h, 7d, 10d, 30d, 60d.
- **Poslednji događaji** (recent events) — choose the period (1 h – 30 days). Each row shows the device name, MAC, IP, connection type, vendor, a description of the change ("IP: old → new", scan size, …) and the time. Click a row to open the device.
- **Novi uređaji po danu** (new devices per day, 30 days), **LAN / Wi-Fi**, **Tip uređaja** (device types), **Top proizvođači** (top vendors).
- **⋮ menu on every chart** — chart style (*Površina* area, *Linija* line, *Barovi* bars), color (10 presets or *Druga…* for any color) and *Debljina linije* (line thickness, 0.5–4 px); donut and bar charts offer six palettes. These choices are remembered per browser.

## Uređaji (Devices)

The device table supports:

- **Search** (MAC, IP, hostname, DHCP hostname, vendor, name, type), filters by status, LAN/Wi-Fi and *Samo poverljivi* (trusted only — hover the **?** for an explanation).
- **Sorting** by clicking any column header (click again to reverse). IP addresses sort numerically.
- **Resetuj filtere** (reset filters) — clears search, filters and sorting.
- **Kolone** (columns) — choose visible columns; *10/50/100 / str.* page size.
- **Export Excel / Export CSV / Export PDF** — the PDF period selector adds a "new devices per day" chart for the chosen period.

Columns: *Status*, *Tip* (type with icon; **AUTO** = recognized automatically), *MAC*, *IP*, *Hostname*, *NetBIOS* / *mDNS* (names the device announces itself), *Vendor* (*privatna MAC* = randomized private address, vendor cannot be known), *Veza* (LAN/Wi-Fi), *Signal* (Wi-Fi RSSI, green ≥ −60 dBm, yellow ≥ −75 dBm, red below), *Prvi put viđen* / *Poslednji put viđen* (first/last seen), *Naziv* (your name), *Beleška* (notes).

### Device detail

Click a row to open the panel:

- **Osnovne informacije** — IP, hostname, vendor, type, connection (with access point name for Wi-Fi), first/last seen, number of sightings, Wi-Fi signal and SSID, DHCP hostname, switch port.
- **Uptime** — a bar showing online (green) and offline (red) periods since the device was first seen (limited by the history retention); hover a segment for its state, start, end and duration.
- **Prisutnost** (presence) — *Online danas*, *Offline danas* and *Dostupnost danas* (availability) since local midnight, and a chart with time on the horizontal axis and the state (Online / Offline) on the vertical axis for *Danas*, *24h*, *7 dana* or *30 dana*. The points mark the moments a state change was recorded (the device disappeared / came back); the last point is the current state. Hover the chart to see the state under the cursor with its start, end and duration. NDW records state changes, not every individual scan.
- **Korisnička podešavanja** (your settings):
  - *Naziv* — a friendly name.
  - *Tip uređaja* — pick from the suggestions or type your own; a typed type is never changed automatically. Clear it to let the app classify the device again.
  - *Hostname* and *Vendor* — filled automatically (DNS, Omada, vendor database). If you type your own value it is marked **RUČNO** (manual) and locked; clear the field to return to automatic detection.
  - *Beleška* — notes.
  - *Poverljiv uređaj* — trusted device.
- **Istorija IP adresa** — every IP the device has used, with time ranges.
- **Događaji** — the device's events with descriptions.
- *Obriši uređaj* (delete device, with confirmation) and *Sačuvaj izmene* (save).

### Trusted devices

A trusted device is one you know and do not want routine alerts about (family phones, TVs, IoT). All its events are still recorded and shown, but **no e-mail, MQTT event or webhook** is sent when it goes offline, comes back, etc. Security anomalies (network scan, IP conflict, vendor mismatch) are still reported even for trusted devices.

## Ping

Continuous ping monitoring of any targets (LAN devices or internet hosts), configured in *Podešavanja → Ping*.

- **Kartice** (cards) view — per target: average RTT, packet loss, min/max, last measurement time and a chart with ms and time axes. Choose the period: 1h, 6h, 12h, 24h, 7 dana, 10 dana. For longer periods each point is an average over a time bucket (shown above the cards). Red dots on the baseline = target unreachable, yellow = partial packet loss, **▲** at the top = a spike far above the usual range (value in the tooltip). A card turns red when the target is unreachable right now.
- **Merači** (meters) view — one row per target with a colored scale and a cursor at the current RTT. The **Debljina** (thickness) slider makes the rows thinner so many targets fit on one screen; in the most compact setting the RTT value is shown beside the cursor and the scale is hidden.

## Istorija (History)

All recorded events with search, filter by type, *Od* / *Do* (from / to) date-time pickers (format `dd.mm.gggg. ss:mm`, type it or use the calendar), sortable columns, *Resetuj filtere* and paging. Click a row to open the device.

| Event (UI label) | Meaning |
|---|---|
| NOV UREĐAJ | New device detected |
| VRAĆEN / OFFLINE | Device came back / went offline |
| IP PROMENJEN | Device got a different IP |
| HOSTNAME | Hostname changed |
| IZMENA | You edited the device (only changed fields are listed) |
| NALET UREĐAJA | Unusually many new devices in a short time |
| VENDOR MISMATCH | Device fingerprint changed for the same MAC (possible spoofing) |
| IP KONFLIKT | Two MAC addresses use the same IP |
| SKENIRANJE MREŽE | Network scan detected (or a known scanner behaving unusually) |

## Network Time Machine

Pick a moment in the past (date-time picker or the *Sada / −1h / −24h / −7d* buttons) and press *Prikaži*. The page reconstructs which devices were online at that moment, with their IP addresses, and the difference compared with now (*Pojavilo se od tada* — appeared since, *Nestalo od tada* — disappeared since). The table is sortable. How far back you can go depends on the history retention.

## Podešavanja (Settings)

Settings are grouped in sub-tabs; each has a *Kako podesiti* (how to configure) help card. Every option and its default is listed in the [configuration reference](configuration.md).

- **Scanner** — scan interval, offline threshold and minimum absence, interface, probe timeout, network ranges, reverse-DNS; and the **network scan / IP conflict detection** panel with the list of known scanners and what has been learned about each.
- **Ping** — ping interval, RTT color bands and targets: add, enable/disable, edit address and name (✎; a new address clears the old statistics), reorder by dragging the handle or with ▲/▼ (the same order is used on the Ping page), delete.
- **Istorija** — retention of event history and of ping statistics; *Pokreni čišćenje sada* runs the cleanup immediately.
- **MQTT** / **SMTP** — broker / mail server settings with *Test MQTT* / *Send Test Email*. Below them: **Tiha zona** (quiet hours) with time zone.
- **Webhook** — URL, custom headers, *Test Webhook*.
- **Special** - devices you want to hear about every time they come online or go offline (add from the list or by MAC). Notifications go to all configured channels, also for trusted devices; *Obaveštavaj i tokom tihe zone* makes them ignore quiet hours. The card under the help card shows the current state of each special device.
- **Omada** — controller connection; *Testiraj konekciju*, *Učitaj lokacije* (load sites), then pick and save a site.
- **Izgled** (appearance) — theme, custom colors, card style (solid / transparent / glass), opacity, blur, border radius, background image (JPG/PNG/WEBP up to 8 MB) with opacity, blur, brightness, saturation, overlay, position, size and repeat.
- **Backup** — *Export configuration* downloads all settings as JSON; *Import configuration* restores them. *Export / import baze uređaja* exports the device inventory (no history, statistics or ping results) as Excel, CSV or PDF and imports Excel/CSV back (the plain Devices-page export is accepted too). *Proveri fajl* previews the result first; *Spoji* (merge) adds new devices and updates existing ones by MAC, *Zameni* (replace) deletes all devices and their history first. Any import that changes or deletes existing data must be confirmed by typing `IMPORT`. Imported devices start OFFLINE until the scanner sees them.
- **Reset** — deletes all devices and their history (type `RESET` to enable the button). Settings are kept.

Passwords and secrets are never shown again after saving; leave the field empty to keep the stored value.

## Sistem (System)

Two views, switched at the top:

- **Sistemski log** — logs of all services (*Web, Scanner, Pinger, Worker, Sniffer (ARP)*) with level and service filters, text search, start time, sortable columns, and *Download* as a text file.
- **Poslata obaveštenja** — every notification attempt: channel (MQTT, Webhook, E-mail), event, device, destination, status (*POSLATO* sent, *NEUSPEŠNO* failed, *PRESKOČENO* skipped) and the reason or error (for example *tiha zona* — quiet hours, or *poverljiv uređaj* — trusted device).

## Telemetrija (Telemetry)

Live host metrics refreshed every 5 seconds: CPU (total, per core, load average, temperatures when available), memory and swap, disk, network I/O since boot, the web process itself (PID, memory, threads) and system information (hostname, OS, Python version, uptime).
