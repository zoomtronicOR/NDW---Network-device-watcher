# How detection works

## Discovery

Every scan cycle (`scanner.scan_interval_seconds`):

1. **Probe.** The scanner sends one tiny UDP datagram (to the discard port 9) to every host address in the configured ranges. The datagram itself is irrelevant: to route it, the kernel must resolve each neighbor's MAC address via ARP. No raw sockets are used, so the scanner runs **without any privileges**.
2. **Settle.** Wait `settle_seconds` for ARP replies.
3. **Read** the kernel neighbor table (`ip -j neigh show`). Entries in `FAILED` / `INCOMPLETE` state are ignored; the container's own addresses are skipped.
4. **Reverse DNS** for the found IPs (bounded overall timeout, results that arrive late are simply skipped).

If the neighbor table cannot be read, the cycle is skipped. If a scan returns **zero** devices while devices were online (e.g. the interface or the switch went down), it is treated as a scan problem and **nobody** is marked offline.

## Device identity and states

- The **MAC address is the identity** of a device. A new IP for a known MAC is an `IP_CHANGED` event and an entry in the IP history — never a new device.
- An unknown MAC creates a device with status **NEW** and a `NEW_DEVICE` event. The NEW badge stays until someone opens the device in the UI.
- A device seen again after being offline gets a `DEVICE_RETURNED` event.
- **Offline debounce:** a device becomes OFFLINE only when it has missed `offline_threshold` consecutive scans **and** has not been seen for `offline_grace_seconds` (default 300 s). Phones and ESP/Tuya devices often ignore ARP for a minute or two in power-save mode; without the time condition they produced thousands of false offline/returned pairs.
- **Omada presence:** when the Omada integration is active, a known device that the controller lists as a connected client counts as present even if it skipped the ARP probe.

## Hostname, vendor and type

**Hostname**, in order of priority:
1. A hostname you entered manually (locked; nothing overwrites it).
2. Reverse DNS.
3. The DHCP hostname reported by the Omada controller (only fills an empty hostname or replaces a previous Omada-sourced one).
4. For Omada access points and switches, their name in the controller.
5. NetBIOS name (UDP 137 Node Status - Windows, Samba/NAS, printers) or mDNS name (unicast PTR query to UDP 5353 - Apple, Chromecast, ESPHome, Avahi/Linux, printers). Queried in a background thread of the scanner: new, returned and re-addressed devices right away, others every 6 hours. Stored in their own columns; used for the hostname only when it is otherwise empty.

**Vendor** comes from the MAC's OUI prefix using Wireshark's manufacturer database (IEEE MA-L, MA-M and MA-S blocks). The worker downloads a fresh copy weekly into `data/manuf` and re-applies it to all devices; the copy bundled with the `manuf` Python package is the fallback. Randomized ("private", locally administered) MAC addresses used by phones and VMs have no vendor by definition — the UI shows *privatna MAC*. A manually entered vendor is locked.

**Device type** is classified automatically for devices whose type is empty or was set automatically before (marked **AUTO**). Signals, strongest first:

1. Omada infrastructure list — access point, switch, gateway.
2. The default gateway IP → Router.
3. Hostname keywords (e.g. `iphone`, `galaxy`, `laptop`, `chromecast`, `printer`, `esp32`, `tasmota`, `proxmox`, …).
4. The Omada client fingerprint, when the controller provides one.
5. Vendor keywords (e.g. Espressif/Tuya/Shelly → IOT, Hikvision/Dahua → Camera, Synology/QNAP → NAS, Proxmox → Server). Phone makers only count as *Telefon* for Wi-Fi devices, because they also make TVs and laptops.
6. A private MAC on Wi-Fi with no other hint → Telefon.

If nothing matches, the type stays empty rather than guessing. A type you type yourself is never changed.

## Network scan detection

Scan detection needs to see **who is asking**, which the neighbor table cannot tell. A separate service, `networkwatcher-sniffer`, opens a packet socket that the kernel filters to ARP frames only (ethertype 0x0806). It never sends anything and is the only process with `CAP_NET_RAW`.

ARP requests are broadcast, so the listener sees every host's ARP requests on the segment. A sender that asks for at least `threshold_hosts` (default 30) **different** IP addresses within `window_seconds` (60) is reported as `SCAN_DETECTED`, with its MAC, IP and number of probed addresses. This catches host-discovery tools such as `nmap -sn`, `arp-scan`, Fing and similar. Normal devices ask for a handful of addresses (gateway, a few peers); typical home-automation controllers stay well below the threshold.

The container's own MACs are ignored, and gratuitous ARP (a host announcing its own address) is not counted as scanning. The few duplicate-address probes a DHCP client sends for its new address stay far below the threshold. After an alert, the same source is not reported again for `cooldown_seconds` (also across service restarts).

**Limitation:** this is host discovery in the local segment. A port scan of a single host (e.g. a SYN scan) does not produce ARP sweeps and needs an IDS such as Suricata or Zeek.

### Known scanners

Some devices scan legitimately — network monitoring tools, Home Assistant integrations. Put their MAC in *Poznati skeneri* (`ignore_macs`). For each of them the listener **learns a profile** for 6 hours (no alerts during learning), then reports only deviations:

| Deviation | Rule |
|---|---|
| Scanning much more often | ARP requests in the last hour > 2× the usual hourly average (and at least +300) |
| Scanning more addresses | Distinct targets in the window > 1.5× the usual maximum (and at least +20) |
| New source IP | The MAC appears with an IP it never used before — possibly another device impersonating the known scanner's MAC |

Profiles are kept per hour for the last 24 hours and persisted in the database, so they survive restarts. Hours that triggered an alert are excluded from the baseline, so an anomaly never becomes "normal". The learned values are shown in *Podešavanja → Scanner* under the known-scanner list. Removing a MAC from the list discards its profile.

## IP conflict detection

Two devices using the same IP is detected from two sides:

- **ARP listener:** hosts announce their own IP in every ARP request they broadcast. Two different MACs announcing the same IP within `conflict_window_seconds` (default 10 min) → `IP_CONFLICT`. The window is long because hosts refresh known neighbors with unicast ARP, which the listener cannot see; broadcasts from the two hosts may be minutes apart.
- **Scanner:** the neighbor table holds only one MAC per IP, so a conflict shows up as the IP *flipping* between two MACs across scans: device A was seen with IP X within the last 10 minutes and has not moved to another IP, and now device B answers for X.

**One device, several MACs.** Phones often use a randomized ("private") MAC on one SSID and their real MAC on another; the DHCP server identifies the client by its client-id/hostname and may give both MACs the same IP. MAC addresses that report the **same DHCP hostname** are therefore treated as one device and never reported as a conflict.

Otherwise, DHCP never hands out an address whose lease is still active, so this is practically always a real problem — usually a statically configured address colliding with a DHCP lease. An event is recorded for both devices. While the conflict lasts it is re-reported every 10 minutes (shared cooldown per IP for both sources), so the dashboard's *Aktivni IP konflikti* card (conflicts in the last 15 minutes) stays lit until it is resolved.

## Vendor mismatch (possible MAC spoofing)

The OUI vendor is a pure function of the MAC address, so it can never "change" for the same MAC — vendor-database updates are applied silently. Instead, `VENDOR_MISMATCH` uses the **device fingerprint** reported by the Omada controller (manufacturer / OS detected from the client's traffic and DHCP options): if the fingerprint vendor recorded for a MAC changes, the old and new values are logged. This requires an Omada setup that provides fingerprints; otherwise the check is idle.

## Burst of new devices

Five or more new devices within 10 minutes raise one `ANOMALY_BURST_NEW_DEVICES` event (typical after a guest network opens, or a misconfigured DHCP range), in addition to the individual `NEW_DEVICE` events.

## Notifications

| Channel | Sent for |
|---|---|
| MQTT event topics | new device, offline, returned, scan detected, IP conflict |
| Webhook | new device, offline, returned, burst, vendor mismatch, IP conflict, scan detected |
| E-mail | new device |
| Browser (WebSocket) | new devices, burst, scan detected, IP conflict (toasts); all changes refresh open pages |

Rules applied to MQTT event topics, webhooks and e-mail:

- **Quiet hours** — skipped (events are still recorded and shown in the UI).
- **Trusted devices** — skipped for routine events (new / offline / returned); **security anomalies** (scan, IP conflict, vendor mismatch, burst) are always sent.
- Every attempt is written to the notification log with status *sent*, *failed* or *skipped* and the reason.
- MQTT **state** topics (`device/<mac>/status`, `/ip`, `stats/*`, `devices`) are always updated, also during quiet hours, so Home Assistant always shows the real state.
- An unavailable broker, mail server or webhook never blocks detection; MQTT reconnects with a 60 s back-off.
