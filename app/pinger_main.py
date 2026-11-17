from __future__ import annotations

import logging
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from types import FrameType

from sqlalchemy import select

from app.database import SessionLocal
from app.models.ping_result import PingResult
from app.models.ping_target import PingTarget
from app.services.pinger import ping_once
from app.services.settings_store import get_setting

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("networkwatcher.pinger")

_running = True


def _handle_stop(signum: int, frame: FrameType | None) -> None:
    global _running
    _running = False


def run_once() -> None:
    db = SessionLocal()
    try:
        targets = db.execute(select(PingTarget).where(PingTarget.enabled.is_(True))).scalars().all()
        # In parallel: sequentially, each target's 3-packet ping (~2s) added
        # up, so 9 targets took ~19s per cycle no matter what interval was set.
        outcomes = {}
        if targets:
            with ThreadPoolExecutor(max_workers=min(16, len(targets))) as pool:
                futures = {pool.submit(ping_once, t.address): t.id for t in targets}
                for future, target_id in futures.items():
                    outcomes[target_id] = future.result()
        for target in targets:
            outcome = outcomes[target.id]
            db.add(
                PingResult(
                    target_id=target.id,
                    reachable=outcome.reachable,
                    packet_loss_pct=outcome.packet_loss_pct,
                    rtt_min=outcome.rtt_min,
                    rtt_avg=outcome.rtt_avg,
                    rtt_max=outcome.rtt_max,
                    rtt_mdev=outcome.rtt_mdev,
                )
            )
            logger.debug(
                "ping %s: reachable=%s avg=%s loss=%s%%",
                target.address,
                outcome.reachable,
                outcome.rtt_avg,
                outcome.packet_loss_pct,
            )

        # Retention is handled by networkwatcher-worker (Settings -> Istorija,
        # "Čuvanje ping statistike"), not here every few seconds.

        db.commit()
    except Exception:
        logger.exception("ping cycle failed")
        db.rollback()
    finally:
        db.close()


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    logger.info("networkwatcher-pinger starting")
    while _running:
        cycle_start = time.monotonic()
        run_once()

        db = SessionLocal()
        try:
            interval = get_setting(db, "ping", "interval_seconds", 30)
        finally:
            db.close()

        elapsed = time.monotonic() - cycle_start
        sleep_for = max(0.0, interval - elapsed)
        for _ in range(int(sleep_for * 10)):
            if not _running:
                break
            time.sleep(0.1)

    logger.info("networkwatcher-pinger stopped")


if __name__ == "__main__":
    main()
