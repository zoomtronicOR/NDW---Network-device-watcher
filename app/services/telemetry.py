from __future__ import annotations

import os
import platform
import socket
import time
from datetime import datetime, timezone

import psutil

_process = psutil.Process(os.getpid())
_process.cpu_percent(interval=None)  # prime the internal baseline for later non-blocking calls


def collect_telemetry() -> dict:
    cpu_percent = psutil.cpu_percent(interval=0.2)
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    if hasattr(os, "getloadavg"):
        load1, load5, load15 = os.getloadavg()
    else:
        load1 = load5 = load15 = 0.0

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    disk_io = psutil.disk_io_counters()
    net_io = psutil.net_io_counters()
    boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime_seconds = time.time() - psutil.boot_time()

    temperatures: dict[str, float] = {}
    try:
        raw = psutil.sensors_temperatures()
        for name, entries in raw.items():
            if entries:
                temperatures[name] = entries[0].current
    except (AttributeError, OSError):
        pass  # not exposed inside an unprivileged LXC -- fine, just omit

    proc_mem = _process.memory_info()
    with _process.oneshot():
        proc_info = {
            "pid": _process.pid,
            "rss_bytes": proc_mem.rss,
            "vms_bytes": proc_mem.vms,
            "cpu_percent": _process.cpu_percent(interval=None),
            "num_threads": _process.num_threads(),
            "create_time": datetime.fromtimestamp(_process.create_time(), tz=timezone.utc).isoformat(),
        }

    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_count": psutil.cpu_count(),
        "cpu_percent": cpu_percent,
        "cpu_per_core": cpu_per_core,
        "load_avg": {"1m": load1, "5m": load5, "15m": load15},
        "memory": {"total": mem.total, "used": mem.used, "available": mem.available, "percent": mem.percent},
        "swap": {"total": swap.total, "used": swap.used, "percent": swap.percent},
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free, "percent": disk.percent},
        "disk_io": (
            {"read_bytes": disk_io.read_bytes, "write_bytes": disk_io.write_bytes} if disk_io is not None else None
        ),
        "network_io": {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
        },
        "boot_time": boot_time.isoformat(),
        "uptime_seconds": uptime_seconds,
        "temperatures": temperatures,
        "process": proc_info,
    }
