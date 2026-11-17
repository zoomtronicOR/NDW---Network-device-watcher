# Installation

Network Device Watcher (NDW) is built to run in its own small Linux container on the network it monitors. The reference platform is a **Proxmox VE unprivileged LXC with Debian 12 or 13**; any Debian/Ubuntu host or VM with a network interface on the monitored LAN works the same way.

## 1. Requirements

| Resource | Recommended |
|---|---|
| OS | Debian 12 (bookworm) or 13 (trixie) |
| CPU | 2 vCPU |
| RAM | 1–2 GB |
| Disk | 8–20 GB (see [sizing](operations.md#disk-usage-and-sizing)) |
| Network | Bridged to the LAN you want to monitor (e.g. `vmbr0`), static IP or DHCP reservation |
| Python | 3.11 or newer |
| PostgreSQL | 15+ (the Debian package is fine) |

The host must be **on the same layer-2 segment** as the devices: discovery uses ARP, which does not cross routers. To monitor several VLANs, give the container an interface in each VLAN.

## 2. Create the container (Proxmox)

In the Proxmox UI: *Create CT* → Debian 12/13 template → unprivileged → 2 cores, 1024–2048 MB RAM, 8+ GB disk → network `vmbr0` with a static IPv4 or DHCP. Or from the Proxmox shell:

```bash
pct create 120 local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst \
  --hostname networkwatcher --unprivileged 1 --cores 2 --memory 2048 \
  --rootfs local-lvm:12 --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1
pct start 120
pct enter 120
```

No special container features are required. Both privileged operations NDW needs (raw sockets for `ping` and for the ARP listener) work inside an unprivileged container because they only apply to the container's own network namespace.

## 3. Install packages

```bash
apt update
apt install -y python3 python3-venv python3-pip postgresql iproute2 iputils-ping libcap2-bin git
```

`iproute2` provides `ip neigh`/`ip route` used by the scanner, `iputils-ping` the ping binary, `libcap2-bin` the `setcap` tool.

## 4. Service user and code

```bash
useradd --system --home /opt/networkwatcher --shell /usr/sbin/nologin networkwatcher
usermod -aG systemd-journal networkwatcher   # lets the "Sistem" page read service logs

git clone https://github.com/zoomtronicOR/NDW---Network-device-watcher.git /opt/networkwatcher
cd /opt/networkwatcher
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 5. Database

The database **must use UTF8 encoding** — device names, notes and hostnames may contain non-ASCII characters. On containers created with `LANG=C`, PostgreSQL's default template is `SQL_ASCII`, so create the database explicitly from `template0`:

```bash
sudo -u postgres psql -c "CREATE ROLE networkwatcher LOGIN PASSWORD 'choose-a-strong-password';"
sudo -u postgres psql -c "CREATE DATABASE networkwatcher OWNER networkwatcher ENCODING 'UTF8' LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8' TEMPLATE template0;"
```

Check: `sudo -u postgres psql -At -c "select pg_encoding_to_char(encoding) from pg_database where datname='networkwatcher'"` must print `UTF8`.

## 6. Configuration file

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

```ini
DATABASE_URL=postgresql+psycopg2://networkwatcher:choose-a-strong-password@localhost:5432/networkwatcher
SECRET_KEY=<a long random string, e.g. output of: openssl rand -hex 32>
```

`SECRET_KEY` encrypts the SMTP/MQTT/Omada passwords stored in the database. Keep it safe and **do not change it later** — previously stored secrets could no longer be decrypted (you would have to re-enter them).

Create the schema:

```bash
./venv/bin/alembic upgrade head
```

## 7. Privileges

```bash
# Ping monitoring: raw ICMP for the ping binary only (not for Python)
setcap cap_net_raw+ep "$(command -v ping)"
```

Re-run this after every upgrade of the `iputils-ping` package — reinstalling the binary drops the capability.

The ARP listener (`networkwatcher-sniffer`) gets `CAP_NET_RAW` from its own systemd unit (`AmbientCapabilities`); nothing else to do.

## 8. Services

```bash
chown -R networkwatcher:networkwatcher /opt/networkwatcher
cp deploy/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now networkwatcher-web networkwatcher-scanner networkwatcher-pinger \
                       networkwatcher-worker networkwatcher-sniffer
systemctl status 'networkwatcher-*'
```

| Unit | Purpose |
|---|---|
| `networkwatcher-web` | Web UI + REST API + WebSocket on port 8080 (uvicorn) |
| `networkwatcher-scanner` | Discovery loop, detection engine, Omada sync, notifications |
| `networkwatcher-sniffer` | Passive ARP listener: scan and IP-conflict detection |
| `networkwatcher-pinger` | Ping monitoring of configured targets |
| `networkwatcher-worker` | Hourly retention cleanup, weekly vendor-database refresh |

All units are `enable`d, so they start automatically after a container reboot (PostgreSQL first).

## 9. First start

1. Open `http://<container-ip>:8080`.
2. **Podešavanja → Scanner**: enter the network range(s) to scan, one CIDR per line (e.g. `192.168.1.0/24`), and the interface (`eth0`; empty = automatic). Save. The scanner applies the change on its next cycle.
3. Within a minute the **Uređaji** page fills with devices. All of them start as **NOV** (new); opening a device marks it as seen.
4. Optionally configure MQTT, SMTP, webhook, Omada, quiet hours and appearance — see the [user guide](user-guide.md) and [integrations](integrations.md).

## 10. Optional: reverse proxy (nginx) and HTTPS

NDW has **no login**. Expose it only on a trusted network, or put it behind a proxy that adds authentication. Example with basic auth:

```bash
apt install -y nginx apache2-utils
htpasswd -c /etc/nginx/ndw.htpasswd admin
```

```nginx
# /etc/nginx/sites-available/networkwatcher
server {
    listen 80;
    server_name networkwatcher.local;

    auth_basic "Network Device Watcher";
    auth_basic_user_file /etc/nginx/ndw.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    location /api/ws {                      # WebSocket for live notifications
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

```bash
ln -s /etc/nginx/sites-available/networkwatcher /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

If you use the proxy, bind uvicorn to localhost only by changing `--host 0.0.0.0` to `--host 127.0.0.1` in `networkwatcher-web.service`. Note that the internal endpoint `/api/internal/broadcast` only accepts requests from `127.0.0.1`, so the scanner/sniffer → web relay keeps working. For HTTPS add a certificate (e.g. certbot, or your internal CA) to the server block.

## 11. Upgrading

```bash
cd /opt/networkwatcher
sudo -u networkwatcher git pull
sudo -u networkwatcher ./venv/bin/pip install -r requirements.txt
sudo -u networkwatcher ./venv/bin/alembic upgrade head
cp deploy/systemd/*.service /etc/systemd/system/ && systemctl daemon-reload   # if units changed
systemctl restart networkwatcher-web networkwatcher-scanner networkwatcher-pinger \
                  networkwatcher-worker networkwatcher-sniffer
```

Read [CHANGELOG.md](../CHANGELOG.md) before upgrading. The current version is shown next to the title in the UI and at `GET /api/version`. Browsers revalidate static files on every load, so no hard refresh is needed after an upgrade.

## 12. Backup and restore

**Settings only** — *Podešavanja → Backup → Export configuration* downloads a JSON file with every setting. Secret values are included in encrypted form, so importing them only works on an installation with the same `SECRET_KEY`.

**Everything** (devices, history, settings):

```bash
sudo -u postgres pg_dump -Fc networkwatcher > /root/networkwatcher-$(date +%F).dump
# restore into an empty UTF8 database created as in step 5:
sudo -u postgres pg_restore -d networkwatcher /root/networkwatcher-2026-01-01.dump
```

Also keep a copy of `/opt/networkwatcher/.env` (the `SECRET_KEY`) and `uploads/backgrounds/` (custom background images). Proxmox `vzdump` backups of the whole container are the simplest option.

## 13. Uninstall

```bash
systemctl disable --now networkwatcher-web networkwatcher-scanner networkwatcher-pinger \
                        networkwatcher-worker networkwatcher-sniffer
rm /etc/systemd/system/networkwatcher-*.service && systemctl daemon-reload
sudo -u postgres psql -c "DROP DATABASE networkwatcher;" -c "DROP ROLE networkwatcher;"
rm -rf /opt/networkwatcher
userdel networkwatcher
setcap -r "$(command -v ping)"      # optional: remove the ping capability
```
