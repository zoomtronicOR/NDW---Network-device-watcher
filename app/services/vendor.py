"""MAC -> vendor (OUI) lookup.

The `manuf` package bundles a ~2020 copy of Wireshark's manuf database, so
newer OUI blocks (Proxmox BC:24:11, recent Espressif/Tuya ranges, ...) came
back as unknown. networkwatcher-worker now downloads Wireshark's current
manuf file (IEEE MA-L/MA-M/MA-S, ~3 MB) into data/manuf weekly; every
process picks up a newer file automatically (mtime check). The bundled copy
remains the fallback when no download has happened yet / there's no internet.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from manuf import manuf

logger = logging.getLogger("networkwatcher.vendor")

MANUF_URL = "https://www.wireshark.org/download/automated/data/manuf"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MANUF_PATH = DATA_DIR / "manuf"
_MTIME_CHECK_SECONDS = 600

_lock = threading.Lock()
_parser: manuf.MacParser | None = None
_parser_mtime: float | None = None
_last_check = 0.0


def _load_parser() -> manuf.MacParser:
    global _parser, _parser_mtime, _last_check
    now = time.monotonic()
    with _lock:
        if _parser is not None and now - _last_check < _MTIME_CHECK_SECONDS:
            return _parser
        _last_check = now
        mtime = MANUF_PATH.stat().st_mtime if MANUF_PATH.exists() else None
        if _parser is None or mtime != _parser_mtime:
            if mtime is not None:
                try:
                    _parser = manuf.MacParser(manuf_name=str(MANUF_PATH), update=False)
                    _parser_mtime = mtime
                    return _parser
                except Exception:
                    logger.exception("could not parse %s, falling back to bundled database", MANUF_PATH)
            _parser = manuf.MacParser(update=False)
            _parser_mtime = None
        return _parser


def is_locally_administered(mac_address: str) -> bool:
    """Randomized / "private" MACs (phones, VMs) set bit 1 of the first octet;
    they have no OUI vendor by definition."""
    hex_only = re.sub(r"[^0-9A-Fa-f]", "", mac_address)
    return len(hex_only) >= 2 and bool(int(hex_only[:2], 16) & 0x02)


def lookup_vendor(mac_address: str) -> str | None:
    if is_locally_administered(mac_address):
        return None
    parser = _load_parser()
    try:
        return parser.get_manuf_long(mac_address) or parser.get_manuf(mac_address)
    except Exception:
        return None


def refresh_database(timeout: int = 60) -> tuple[bool, str]:
    """Download the current Wireshark manuf file; replace data/manuf atomically
    only if the download parses and looks complete. Never raises."""
    try:
        req = urllib.request.Request(MANUF_URL, headers={"User-Agent": "NetworkDeviceWatcher/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
    except Exception as e:
        return False, f"preuzimanje nije uspelo: {e}"

    if len(content) < 500_000 or b"\t" not in content[:5000]:
        return False, f"neočekivan sadržaj ({len(content)} bajtova)"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix="manuf.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        test = manuf.MacParser(manuf_name=tmp, update=False)
        if not test.get_manuf("BC:24:11:00:00:01"):
            raise ValueError("test lookup failed")
        os.replace(tmp, MANUF_PATH)
    except Exception as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False, f"neispravna baza: {e}"

    global _last_check
    _last_check = 0.0  # force reload in this process
    return True, f"vendor baza osvežena ({len(content) // 1024} KB)"


def database_age_days() -> float | None:
    if not MANUF_PATH.exists():
        return None
    return (time.time() - MANUF_PATH.stat().st_mtime) / 86400
