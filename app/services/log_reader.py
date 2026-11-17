from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

_UNITS = {
    "web": "networkwatcher-web.service",
    "scanner": "networkwatcher-scanner.service",
    "pinger": "networkwatcher-pinger.service",
    "worker": "networkwatcher-worker.service",
    "sniffer": "networkwatcher-sniffer.service",
}
_UNIT_TO_SOURCE = {unit: name for name, unit in _UNITS.items()}

# journald's own PRIORITY field is nearly always 6 (info) here, since both
# services just log to stdout rather than tagging priority explicitly -- the
# real level is embedded as text by Python's logging formatter / uvicorn's
# own log lines, so we parse it out of the message first and only fall back
# to PRIORITY when nothing matches (e.g. a bare traceback continuation line).
_LEVEL_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}[ T][\d:,.]+\s+(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b"),
    re.compile(r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL):"),
]

# journald tags stdout and stderr with the same default priority here (no
# SyslogLevelPrefix/StandardError split configured), so an unhandled Python
# exception's traceback -- printed to stderr with no level prefix at all --
# would otherwise fall back to PRIORITY and show up as INFO. Recognize it by
# shape instead.
_ERROR_TEXT_PATTERNS = [
    re.compile(r"^Traceback \(most recent call last\):"),
    re.compile(r"^\s{2,}File \".*\", line \d+"),
    re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception):\s"),
]

_PRIORITY_FALLBACK = {
    "0": "ERROR",
    "1": "ERROR",
    "2": "ERROR",
    "3": "ERROR",
    "4": "WARNING",
    "5": "INFO",
    "6": "INFO",
    "7": "DEBUG",
}


def _detect_level(message: str, priority: str) -> str:
    for pattern in _LEVEL_PATTERNS:
        m = pattern.match(message)
        if m:
            level = m.group(1)
            return "ERROR" if level == "CRITICAL" else level
    for pattern in _ERROR_TEXT_PATTERNS:
        if pattern.match(message):
            return "ERROR"
    return _PRIORITY_FALLBACK.get(priority, "INFO")


@dataclass
class LogEntry:
    timestamp: datetime
    level: str
    source: str
    message: str


def read_logs(
    source: str = "all",
    limit: int = 5000,
    since: str | None = None,
    until: str | None = None,
    search: str | None = None,
) -> list[LogEntry]:
    cmd = ["journalctl", "-o", "json", "--no-pager", "-q", "-n", str(limit)]

    if source == "all":
        for unit in _UNITS.values():
            cmd += ["-u", unit]
    elif source in _UNITS:
        cmd += ["-u", _UNITS[source]]
    else:
        return []

    if since:
        cmd += ["--since", since]
    if until:
        cmd += ["--until", until]
    if search:
        cmd += ["-g", search]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    entries: list[LogEntry] = []
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue

        message = row.get("MESSAGE", "")
        if isinstance(message, list):  # journald represents non-UTF8 fields as raw byte arrays
            message = bytes(message).decode("utf-8", errors="replace")

        unit = row.get("_SYSTEMD_UNIT", "")
        src = _UNIT_TO_SOURCE.get(unit, "?")
        priority = row.get("PRIORITY", "6")
        level = _detect_level(message, priority)

        timestamp_us = row.get("__REALTIME_TIMESTAMP")
        timestamp = (
            datetime.fromtimestamp(int(timestamp_us) / 1_000_000, tz=timezone.utc)
            if timestamp_us
            else datetime.now(timezone.utc)
        )

        entries.append(LogEntry(timestamp=timestamp, level=level, source=src, message=message))

    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries
