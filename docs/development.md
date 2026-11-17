# Development

## Project layout

```text
app/
├── main.py              FastAPI app: routers, static files, /api/health, /api/version
├── version.py           __version__ (single source of truth)
├── config.py            .env settings (DATABASE_URL, SECRET_KEY)
├── database.py          SQLAlchemy engine/session (UTF-8 client encoding)
├── scanner_main.py      scanner service loop
├── sniffer_main.py      ARP listener service
├── pinger_main.py       ping service
├── worker_main.py       retention + vendor database service
├── api/                 REST routers (devices, events, stats, charts, settings, ping, export,
│                        logs, notifications, timemachine, telemetry, ws)
├── models/              SQLAlchemy models
├── schemas/             Pydantic request/response models
├── services/
│   ├── scanner.py           ARP/neighbor-table discovery
│   ├── detector.py          detection engine (states, events, debounce, conflicts, burst)
│   ├── arp_monitor.py       pure logic for scan / IP-conflict / known-scanner detection
│   ├── device_classifier.py automatic device type
│   ├── vendor.py            OUI lookup + database refresh
│   ├── omada_client.py      TP-Link Omada Open API
│   ├── mqtt_client.py, ha_discovery.py, smtp_client.py, webhook_client.py
│   ├── notification_gate.py quiet hours / trusted rules
│   ├── notification_log.py  notification log writer
│   ├── retention.py, exporter.py, pdf_report.py, telemetry.py, log_reader.py, …
└── static/              web UI (HTML, CSS, JS — no build step)
deploy/systemd/          unit files
migrations/              Alembic migrations
docs/                    documentation and screenshots
tools/mock_server.py     demo server with synthetic data
```

## Running locally

Requirements: Python 3.11+, PostgreSQL with a UTF8 database, Linux with `iproute2` (the scanner reads `ip neigh`).

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env            # point DATABASE_URL at your database
./venv/bin/alembic upgrade head
./venv/bin/uvicorn app.main:app --reload --port 8080       # web
./venv/bin/python -m app.scanner_main                       # scanner (another terminal)
```

The sniffer needs `CAP_NET_RAW` (run it with `sudo` for testing, or via its systemd unit). The pinger needs the capability on the `ping` binary.

### UI work without a network or database

`tools/mock_server.py` serves the real `app/static` files plus a synthetic API (standard library only):

```bash
python tools/mock_server.py --port 8765
```

It generates fictional devices, events, ping series and settings on start. The screenshots in `docs/screenshots/` are taken from it with a headless browser, e.g.:

```bash
msedge --headless=new --window-size=1500,1240 --virtual-time-budget=6000 \
       --screenshot=docs/screenshots/dashboard.png http://127.0.0.1:8765/
```

Never take README screenshots from a real installation — they would publish real device names, addresses and MACs.

## Database migrations

```bash
./venv/bin/alembic revision -m "short description"   # write upgrade()/downgrade() by hand
./venv/bin/alembic upgrade head
```

Prefer server defaults for new non-null columns so existing rows migrate cleanly. Event and connection types are plain strings — adding a new event type needs no migration (add it to `app/models/enums.py` and to `EVENT_META` in `js/common.js`).

## Conventions

- **Detection must never be blocked** by integrations: every external call catches its own errors and logs them.
- **Do not invent data**: unknown values stay empty (`null`) rather than guessed.
- New settings: add defaults in `app/api/settings.py`, fields in `app/schemas/settings.py`, UI in `settings.html`/`settings.js`, and document them in `docs/configuration.md`.
- Comments may reference sections of the internal design specification as `§N`.
- UI text is Serbian (Latin script); code, comments, API and docs are English.
- Browser-only preferences go through `Prefs` in `common.js` (localStorage, always optional).
- Tables: mark sortable headers with `data-sort` and use `bindSortableHeaders()`; server-side sorting for paged lists.

## Releasing a new version

The project uses [Semantic Versioning](https://semver.org): MAJOR for breaking changes (e.g. incompatible API or install steps), MINOR for new features, PATCH for fixes.

1. Update `__version__` in `app/version.py` (also the badge at the top of `README.md`).
2. Add a section to `CHANGELOG.md` (Added / Changed / Fixed) and a link at the bottom.
3. If needed, regenerate screenshots with the mock server.
4. Commit, then tag and push:

```bash
git commit -am "Release 1.1.0"
git tag -a v1.1.0 -m "Network Device Watcher 1.1.0"
git push origin main v1.1.0
```

5. On GitHub: *Releases → Draft a new release* → choose the tag → paste the CHANGELOG section.

The running version is visible next to the title in the UI and at `GET /api/version`.
