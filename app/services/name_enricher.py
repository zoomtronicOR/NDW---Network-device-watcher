"""Background NetBIOS / mDNS name enrichment (runs as a thread in the scanner).

Never blocks the scan loop: every 30 s it picks online devices that are due
(never queried in this process, IP changed, or last query older than
REFRESH_HOURS) and queries them in parallel with short timeouts.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.database import SessionLocal
from app.models.device import Device
from app.services.name_resolver import mdns_name, netbios_name, short_mdns

logger = logging.getLogger("networkwatcher.names")

REFRESH_HOURS = 6
ROUND_SECONDS = 30
MAX_PER_ROUND = 64


class NameEnricher(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="name-enricher", daemon=True)
        self._stop_event = threading.Event()
        self._last: dict[str, tuple[float, str]] = {}  # mac -> (monotonic time of query, ip queried)

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        self._stop_event.wait(5)  # let the first scan finish
        while not self._stop_event.is_set():
            try:
                self.run_round()
            except Exception:
                logger.exception("name enrichment round failed")
            self._stop_event.wait(ROUND_SECONDS)

    def run_round(self) -> int:
        now = time.monotonic()
        db = SessionLocal()
        try:
            online = db.execute(
                select(Device.mac_address, Device.ip_address).where(
                    Device.is_online.is_(True), Device.ip_address.is_not(None)
                )
            ).all()
            # Forget devices that went offline, so they are queried again as
            # soon as they return.
            online_macs = {mac for mac, _ in online}
            for mac in [m for m in self._last if m not in online_macs]:
                del self._last[mac]
            due = [(mac, ip) for mac, ip in online if self._due_raw(mac, ip, now)][:MAX_PER_ROUND]
            if not due:
                return 0

            def lookup(item):
                mac, ip = item
                return mac, ip, netbios_name(ip), mdns_name(ip)

            with ThreadPoolExecutor(max_workers=min(32, len(due))) as pool:
                results = list(pool.map(lookup, due))

            changed = 0
            for mac, ip, nb, md in results:
                self._last[mac] = (now, ip)
                device = db.execute(select(Device).where(Device.mac_address == mac)).scalar_one_or_none()
                if device is None or device.ip_address != ip:
                    continue  # moved meanwhile; it will be due again
                touched = False
                if nb and nb != device.netbios_hostname:
                    device.netbios_hostname = nb
                    touched = True
                if md and md != device.mdns_hostname:
                    device.mdns_hostname = md
                    touched = True
                # Fill an empty hostname (never overwrite DNS / Omada / manual names).
                if not device.hostname and not device.hostname_locked and not device.dhcp_hostname:
                    candidate = short_mdns(md) or nb
                    if candidate:
                        device.hostname = candidate
                        touched = True
                changed += touched
            if changed:
                db.commit()
            found_nb = sum(1 for r in results if r[2])
            found_md = sum(1 for r in results if r[3])
            logger.info(
                "name lookup: %d queried, NetBIOS %d, mDNS %d, %d device(s) updated",
                len(results), found_nb, found_md, changed,
            )
            return changed
        finally:
            db.close()

    def _due_raw(self, mac: str, ip: str, now: float) -> bool:
        last = self._last.get(mac)
        if last is None:
            return True
        queried_at, last_ip = last
        return last_ip != ip or now - queried_at > REFRESH_HOURS * 3600
