from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

_RTT_STATS_RE = re.compile(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)")
_LOSS_RE = re.compile(r"([\d.]+)% packet loss")


@dataclass
class PingOutcome:
    reachable: bool
    packet_loss_pct: float
    rtt_min: float | None = None
    rtt_avg: float | None = None
    rtt_max: float | None = None
    rtt_mdev: float | None = None


def ping_once(address: str, count: int = 3, timeout: int = 2) -> PingOutcome:
    """Real ICMP ping via the system `ping` binary (needs CAP_NET_RAW on that
    binary -- granted via `setcap cap_net_raw+ep` at deploy time rather than
    running the whole app as root, per §38).
    """
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", str(timeout), address],
            capture_output=True,
            text=True,
            timeout=count * timeout + 5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return PingOutcome(reachable=False, packet_loss_pct=100.0)

    loss_match = _LOSS_RE.search(result.stdout)
    loss = float(loss_match.group(1)) if loss_match else 100.0

    stats_match = _RTT_STATS_RE.search(result.stdout)
    if stats_match and loss < 100:
        return PingOutcome(
            reachable=True,
            packet_loss_pct=loss,
            rtt_min=float(stats_match.group(1)),
            rtt_avg=float(stats_match.group(2)),
            rtt_max=float(stats_match.group(3)),
            rtt_mdev=float(stats_match.group(4)),
        )
    return PingOutcome(reachable=False, packet_loss_pct=loss)
