from __future__ import annotations

import logging
import signal
import time
from types import FrameType

from app.database import SessionLocal
from app.services.retention import cleanup_history, cleanup_ping_results
from app.services.settings_store import get_setting
from app.services.vendor import database_age_days, lookup_vendor, refresh_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("networkwatcher.worker")

_running = True
_CLEANUP_INTERVAL_SECONDS = 3600


def _handle_stop(signum: int, frame: FrameType | None) -> None:
    global _running
    _running = False


_VENDOR_DB_MAX_AGE_DAYS = 7


def refresh_vendors() -> None:
    """Weekly OUI database refresh, then backfill every device's vendor
    (offline devices too -- the scanner only re-looks-up devices it sees).
    Manually entered vendors (vendor_locked) are never touched."""
    from sqlalchemy import select

    from app.models.device import Device

    age = database_age_days()
    if age is None or age > _VENDOR_DB_MAX_AGE_DAYS:
        ok, message = refresh_database()
        (logger.info if ok else logger.warning)("vendor database: %s", message)

    db = SessionLocal()
    try:
        changed = 0
        for device in db.execute(select(Device).where(Device.vendor_locked.is_(False))).scalars():
            vendor = lookup_vendor(device.mac_address)
            if vendor and vendor != device.vendor:
                device.vendor = vendor
                changed += 1
        if changed:
            db.commit()
            logger.info("vendor backfill: %d device(s) updated", changed)
    except Exception:
        logger.exception("vendor backfill failed")
        db.rollback()
    finally:
        db.close()


def run_once() -> None:
    db = SessionLocal()
    try:
        retention_days = get_setting(db, "history", "retention_days", 90)
        counts = cleanup_history(db, retention_days)
        if any(counts.values()):
            logger.info(
                "history cleanup: retention_days=%s device_events=%d ip_history=%d notification_log=%d",
                retention_days,
                counts["device_events"],
                counts["ip_history"],
                counts["notification_log"],
            )
        else:
            logger.info("history cleanup: nothing to delete (retention_days=%s)", retention_days)

        ping_days = get_setting(db, "history", "ping_retention_days", 10)
        ping_deleted = cleanup_ping_results(db, ping_days)
        logger.info("ping cleanup: retention_days=%s deleted=%d", ping_days, ping_deleted)
    except Exception:
        logger.exception("history cleanup cycle failed")
        db.rollback()
    finally:
        db.close()


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    logger.info("networkwatcher-worker starting")
    while _running:
        run_once()
        refresh_vendors()
        for _ in range(_CLEANUP_INTERVAL_SECONDS * 10):
            if not _running:
                break
            time.sleep(0.1)

    logger.info("networkwatcher-worker stopped")


if __name__ == "__main__":
    main()
