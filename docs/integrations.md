# Integrations

All integrations are optional and independent. If one is not configured or its server is unreachable, detection and the rest of the application keep working. Every notification attempt is visible in *Sistem → Poslata obaveštenja*.

## MQTT

Configure in *Podešavanja → MQTT* and press *Test MQTT*. Topics with the default base topic `networkwatcher`:

| Topic | Retained | Payload |
|---|---|---|
| `networkwatcher/status` | yes | `online` while connected, `offline` (last will) |
| `networkwatcher/devices` | per `retain` | JSON array `[{"mac", "ip", "status"}]`, every scan |
| `networkwatcher/stats/total` · `online` · `wifi` · `lan` | per `retain` | number, every scan |
| `networkwatcher/stats/last_new_device` | per `retain` | MAC of the most recently discovered device |
| `networkwatcher/stats/new_device_flag` | per `retain` | `ON` while any device is unacknowledged NEW, else `OFF` |
| `networkwatcher/device/<mac>/status` | per `retain` | `online` / `offline` |
| `networkwatcher/device/<mac>/ip` | per `retain` | current IP |
| `networkwatcher/events/new_device` | no | event JSON |
| `networkwatcher/events/offline` | no | event JSON |
| `networkwatcher/events/returned` | no | event JSON |
| `networkwatcher/events/scan_detected` | no | event JSON + `target_count`, `window_seconds`, `reason` (known scanner) |
| `networkwatcher/events/ip_conflict` | no | event JSON + `conflicting_macs` |
| `networkwatcher/events/special` | no | special device online/offline: event JSON + `state` (`online`/`offline`), `name` |

`<mac>` is normalized to lowercase with underscores, e.g. `aa_bb_cc_dd_ee_ff`. Event JSON: `{"mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.1.45", "event": "NEW_DEVICE"}`.

State and stats topics are always published; event topics follow the quiet-hours and trusted-device rules ([details](detection.md#notifications)).

### Home Assistant

Enable *Home Assistant Discovery* (prefix `homeassistant`). NDW publishes retained discovery configs for one HA device, "Network Device Watcher", with these entities:

| Entity | Source topic |
|---|---|
| `sensor` Network Devices Total | `stats/total` |
| `sensor` Network Devices Online | `stats/online` |
| `sensor` Network Devices Wi-Fi | `stats/wifi` |
| `sensor` Network Devices LAN | `stats/lan` |
| `sensor` Network Last New Device | `stats/last_new_device` |
| `binary_sensor` Network New Device | `stats/new_device_flag` |

Per-device presence can be added manually, e.g.:

```yaml
mqtt:
  binary_sensor:
    - name: "Phone - Ana home"
      state_topic: "networkwatcher/device/9a_65_4e_bf_52_00/status"
      payload_on: "online"
      payload_off: "offline"
      device_class: presence
```

Example automation on a network scan:

```yaml
automation:
  - alias: "Network scan detected"
    trigger:
      - platform: mqtt
        topic: networkwatcher/events/scan_detected
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Network scan"
          message: "{{ trigger.payload_json.mac }} ({{ trigger.payload_json.ip }}) probed {{ trigger.payload_json.target_count }} addresses"
```

## Webhook

*Podešavanja → Webhook*: URL plus optional headers (`Name: value`, one per line, e.g. `Authorization: Bearer <token>`). NDW sends an HTTP **POST** with `Content-Type: application/json` and an 8-second timeout:

```json
{"event": "NEW_DEVICE", "mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.1.45"}
```

| `event` | Extra fields |
|---|---|
| `NEW_DEVICE`, `DEVICE_OFFLINE`, `DEVICE_RETURNED`, `VENDOR_MISMATCH` | – |
| `IP_CONFLICT` | `conflicting_macs` |
| `SPECIAL_DEVICE` | `state` (`online`/`offline`), `name` |
| `SCAN_DETECTED` | `target_count`, `window_seconds`, `reason` (only for known scanners) |
| `ANOMALY_BURST_NEW_DEVICES` | `new_devices` (list of MACs); `mac`/`ip` are `null` |
| `TEST` (from *Test Webhook*) | `message` |

Works directly with n8n, Node-RED, Home Assistant webhooks, Zapier/Make, or a small bridge to Discord/Telegram. The URL query string is not stored in the notification log (tokens often live there).

## E-mail (SMTP)

*Podešavanja → SMTP*: server, port, security (*Ništa* / STARTTLS / SSL/TLS), credentials, sender, recipients (comma-separated), subject prefix. *Send Test Email* reports `SMTP connection successful` or the exact error. An e-mail is sent for every **new device**:

```text
Subject: [Network Watcher] New device detected

Novi uređaj detektovan na mreži.

IP: 192.168.1.45
MAC: AA:BB:CC:DD:EE:FF
Vendor: Espressif Inc.
Connection: WIFI
First seen: 31.08.2026 09:12:44
```

Gmail: use `smtp.gmail.com`, port 587, STARTTLS and an **App Password** (requires 2-step verification on the Google account).

## TP-Link Omada

Plain IP scanning only sees the container's Ethernet interface, so without a controller every device looks like LAN. With the Omada Open API, NDW gets for every client: Wi-Fi vs. wired, SSID, RSSI, access point, switch and port, DHCP hostname, and presence of sleeping Wi-Fi clients. Access points and switches managed by the controller are named and typed automatically.

### Create an API application on the controller

*Omada controller → Settings → Platform Integration → Open API → Add New App*:

- **Mode: Client** (client-credentials). The *Authorization Code* mode needs an interactive browser login and is rejected for a background service ("Client Id Or Client Secret is Invalid").
- **Role: Viewer** — read-only is enough; NDW never changes anything on the controller.
- **Site:** the site(s) the app may access.

Copy the **Client Secret** immediately — later it is shown masked. Note the **Omada ID** (shown on the same page) and **Client ID**.

### Connect

*Podešavanja → Omada*: enable, enter *Controller URL* (e.g. `https://192.168.1.10:8043`), leave *Proveri SSL sertifikat* off for a self-signed certificate, enter Omada ID, Client ID and Client Secret, save. Press *Testiraj konekciju*, then *Učitaj lokacije*, **pick the site and save again** — synchronization does nothing until a site is saved.

The access token is cached (~2 h) and renewed automatically; the infrastructure device list is cached for 10 minutes. If the controller is unreachable, that cycle simply runs without Omada data — devices keep their last known Wi-Fi details and are not switched to LAN.

### Fingerprints

The controller's client manufacturer/OS fingerprints (used for `VENDOR_MISMATCH` and as a device-type hint) are only available when the Omada setup provides them; on many setups they are reported as "Unknown", in which case these features stay idle.
