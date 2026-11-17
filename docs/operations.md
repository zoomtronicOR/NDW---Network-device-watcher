# Operations & troubleshooting

## Health at a glance

- The **status strip** on the dashboard shows every component. *Scanner* turns red if no device was seen for 3 scan intervals, *MQTT* / *Omada* if their last successful contact is older than that, *ARP sniffer* if its heartbeat (every 30 s) is older than 2 minutes.
- `GET /api/health` → `{"status": "ok", "version": …}` for external monitoring (e.g. Uptime Kuma).
- `systemctl status 'networkwatcher-*'`

## Logs

All services log to journald. In the UI: *Sistem → Sistemski log* (filter by service and level, download). On the host:

```bash
journalctl -u networkwatcher-scanner -f          # one "scan complete: seen=… new=… offline=…" line per cycle
journalctl -u networkwatcher-sniffer -f          # SCAN_DETECTED / IP_CONFLICT warnings
journalctl -u networkwatcher-worker --since today # retention and vendor-database refresh
journalctl -u networkwatcher-web -p warning
```

Every e-mail/MQTT/webhook attempt is listed in *Sistem → Poslata obaveštenja* with the reason when it was skipped or failed.

## Disk usage and sizing

| Data | Growth | Controlled by |
|---|---|---|
| `ping_results` | targets × (86 400 / ping interval) rows per day, ≈ 100 bytes each incl. index | *Čuvanje ping statistike* (default 10 days) |
| `device_events` | depends on how often devices come and go | *Čuvanje istorije* (default 90 days) |
| `notification_log`, `ip_history` | small | *Čuvanje istorije* |

Example: 10 ping targets every 5 s for 10 days ≈ 1.7 M rows ≈ 170–250 MB. A typical home network with 100 devices needs well under 1 GB in total. Check sizes with:

```bash
sudo -u postgres psql -d networkwatcher -c "select relname, pg_size_pretty(pg_total_relation_size(relid)) from pg_statio_user_tables order by pg_total_relation_size(relid) desc;"
```

Cleanup runs hourly in the worker; *Podešavanja → Istorija → Pokreni čišćenje sada* runs it immediately.

## Common problems

**Saving a device name with č/ć/š/ž/đ fails, or hostnames with special characters break.**
The database was created with `SQL_ASCII` encoding. Check with `psql -At -c "select pg_encoding_to_char(encoding) from pg_database where datname='networkwatcher'"`. Fix: stop the services, `pg_dump -Fc`, rename or drop the old database, create a new one with `ENCODING 'UTF8' … TEMPLATE template0` ([installation step 5](installation.md#5-database)), `pg_restore`, start the services.

**No devices are found.**
Check *Podešavanja → Scanner*: the network range must be the subnet the container is actually in, and the interface must exist (`ip -br addr`). The scanner log shows `scan failed` if `ip neigh` could not be read. ARP does not cross routers — devices in other VLANs need an interface in that VLAN.

**Devices flap between OFFLINE and VRAĆEN.**
Increase *Minimalna odsutnost pre OFFLINE* (e.g. 600 s) or *Offline threshold*. With TP-Link Omada configured, associated Wi-Fi clients count as present even when they ignore ARP.

**Every device suddenly went offline at the same time.**
A scan that sees nothing while devices were online is ignored, so this normally means the network really was down (power cut, switch reboot). The devices return on the next successful scan.

**The ARP sniffer chip is red / no scans are ever detected.**
`systemctl status networkwatcher-sniffer` and its journal. `Operation not permitted` on start means the capability was not granted — the unit must contain `AmbientCapabilities=CAP_NET_RAW` and `CapabilityBoundingSet=CAP_NET_RAW`. Check *Podešavanja → Scanner* that detection is enabled and that the device you expect is not in the *Poznati skeneri* list (known scanners are only reported when they deviate from their learned behavior, and not at all during the first 6 hours).

**Ping shows every target as unreachable.**
The capability on the ping binary is missing (typically after an `iputils-ping` upgrade): `getcap $(command -v ping)` must print `cap_net_raw=ep`. Re-run `setcap cap_net_raw+ep "$(command -v ping)"`.

**MQTT shows Offline.**
Use *Test MQTT* for the exact error (wrong host/port, credentials, TLS). After a failed connection the client waits 60 s before the next attempt.

**Omada shows Offline or Wi-Fi data is missing.**
*Testiraj konekciju* shows the controller's error. "Client Id Or Client Secret is Invalid" usually means the Open API app was created in *Authorization Code* mode instead of *Client* mode. Synchronization only starts after a site has been loaded **and saved**.

**No e-mails / MQTT events / webhooks arrive.**
Look at *Sistem → Poslata obaveštenja*: *PRESKOČENO — tiha zona* (quiet hours; check the time zone setting) or *poverljiv uređaj* (the device is trusted) explain most cases; *NEUSPEŠNO* shows the server's error.

**Real IP conflicts are not detected.**
Conflicts are visible only if both devices are on the monitored segment. Increase *Prozor za IP konflikt* if the two devices rarely broadcast ARP.

**The UI looks outdated after an upgrade.**
Static files are revalidated on every load; if an intermediate proxy caches aggressively, clear its cache or reload with Ctrl+Shift+R.

## Changing the server's IP or moving to another network

Change the container's address as usual, then update *Mrežni opsezi*. To start a fresh inventory on a new network, use *Podešavanja → Reset* (deletes devices and their history, keeps all settings).
