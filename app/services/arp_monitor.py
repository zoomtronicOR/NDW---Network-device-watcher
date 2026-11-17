"""Passive ARP observation for SCAN_DETECTED (§8.3) and IP_CONFLICT (8.2).

The periodic scanner only reads the kernel neighbor table, which records
*who answered*, never *who asked* -- so it can neither see another host
sweeping the subnet nor two MACs fighting over one IP (the neighbor table
keeps exactly one MAC per IP). Both need the raw ARP frames themselves.

This module is pure logic (no sockets, no DB) so it stays unit-testable; the
privileged packet capture lives in app/sniffer_main.py, a separate small
service that is the only process granted CAP_NET_RAW (§38).
"""

from __future__ import annotations

import socket
import struct
from collections import deque
from dataclasses import dataclass, field

ETH_P_ARP = 0x0806
ARP_REQUEST = 1
ARP_REPLY = 2


@dataclass
class ArpPacket:
    op: int
    sender_mac: str
    sender_ip: str
    target_ip: str


def parse_arp_frame(frame: bytes) -> ArpPacket | None:
    """Ethernet II frame -> ARP fields (IPv4-over-Ethernet only)."""
    if len(frame) < 42:
        return None
    ethertype = struct.unpack("!H", frame[12:14])[0]
    offset = 14
    if ethertype == 0x8100:  # single 802.1Q tag
        if len(frame) < 46:
            return None
        ethertype = struct.unpack("!H", frame[16:18])[0]
        offset = 18
    if ethertype != ETH_P_ARP:
        return None
    arp = frame[offset : offset + 28]
    if len(arp) < 28:
        return None
    htype, ptype, hlen, plen, op = struct.unpack("!HHBBH", arp[:8])
    if htype != 1 or ptype != 0x0800 or hlen != 6 or plen != 4:
        return None
    sender_mac = ":".join(f"{b:02X}" for b in arp[8:14])
    return ArpPacket(
        op=op,
        sender_mac=sender_mac,
        sender_ip=socket.inet_ntoa(arp[14:18]),
        target_ip=socket.inet_ntoa(arp[24:28]),
    )


@dataclass
class ScanAlert:
    mac: str
    ip: str | None
    target_count: int
    window_seconds: int
    # Set for a *known* scanner that deviated from its learned behaviour.
    reason: str | None = None
    known_scanner: bool = False


@dataclass
class ConflictAlert:
    ip: str
    macs: list[str]


@dataclass
class ArpMonitorConfig:
    scan_enabled: bool = True
    scan_threshold: int = 30
    scan_window_seconds: int = 60
    conflict_enabled: bool = True
    conflict_window_seconds: int = 60
    cooldown_seconds: int = 600
    # "Known scanners" (e.g. Watch Your LAN): their *usual* sweeping is not
    # reported, only deviations from their learned profile.
    ignore_macs: set[str] = field(default_factory=set)
    learning_seconds: int = 6 * 3600


@dataclass
class ScannerProfile:
    """Learned behaviour of one known scanner, in hourly buckets so it does
    not depend on splitting traffic into individual sweeps (a scanner that
    never pauses longer than the window would look like one endless sweep).
    Wall-clock hour keys so it can be persisted and survive restarts.

    hours: {hour_index: [arp_requests, max_distinct_targets_in_window, flagged]}
    """

    first_seen: float
    hours: dict[str, list[int]] = field(default_factory=dict)
    ips: list[str] = field(default_factory=list)  # sender IPs seen (most recent last)

    def to_dict(self) -> dict:
        return {"first_seen": self.first_seen, "hours": self.hours, "ips": self.ips}

    @classmethod
    def from_dict(cls, d: dict) -> "ScannerProfile":
        return cls(
            first_seen=float(d.get("first_seen", 0)),
            hours={str(k): [int(x) for x in v] for k, v in (d.get("hours") or {}).items()},
            ips=[str(x) for x in d.get("ips", [])],
        )

    def baseline_hours(self, current_hour: int) -> list[list[int]]:
        """Completed, non-flagged hours of the last 24h."""
        return [
            v for k, v in self.hours.items() if current_hour - 24 <= int(k) < current_hour and not v[2]
        ]

    def prune(self, current_hour: int) -> None:
        for k in [k for k in self.hours if int(k) < current_hour - 25]:
            del self.hours[k]

    def summary(self, wall: float, learning_seconds: int) -> dict:
        base = self.baseline_hours(int(wall // 3600))
        maxes = sorted(v[1] for v in base)
        return {
            "learning": wall - self.first_seen < learning_seconds,
            "learning_until": self.first_seen + learning_seconds,
            "requests_per_hour": round(sum(v[0] for v in base) / len(base)) if base else None,
            "typical_targets": maxes[len(maxes) // 2] if maxes else None,
            "max_targets": maxes[-1] if maxes else None,
            "hours_observed": len(base),
            "ips": self.ips,
        }


class ArpMonitor:
    def __init__(self, config: ArpMonitorConfig, own_macs: set[str], profiles: dict[str, ScannerProfile] | None = None) -> None:
        self.config = config
        self.own_macs = {m.upper() for m in own_macs}
        self.profiles: dict[str, ScannerProfile] = profiles or {}
        self._requests: dict[str, deque[tuple[float, str]]] = {}
        self._last_ip: dict[str, str] = {}
        self._claims: dict[str, dict[str, float]] = {}
        self._scan_cooldown: dict[str, float] = {}
        self._conflict_cooldown: dict[str, float] = {}
        self._recent: dict[str, deque[float]] = {}  # known scanner -> request wall times, last hour

    def observe(self, pkt: ArpPacket, now: float, wall: float | None = None) -> list[ScanAlert | ConflictAlert]:
        wall = wall if wall is not None else now
        mac = pkt.sender_mac.upper()
        if mac in self.own_macs or mac in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
            return []

        alerts: list[ScanAlert | ConflictAlert] = []
        has_ip = pkt.sender_ip != "0.0.0.0"
        if has_ip:
            self._last_ip[mac] = pkt.sender_ip
        known = mac in self.config.ignore_macs

        # --- host-discovery sweep: one sender asking for many distinct targets ---
        if self.config.scan_enabled and pkt.op == ARP_REQUEST and pkt.sender_ip != pkt.target_ip:
            window = self.config.scan_window_seconds
            dq = self._requests.setdefault(mac, deque())
            dq.append((now, pkt.target_ip))
            while dq and now - dq[0][0] > window:
                dq.popleft()
            distinct = len({t for _, t in dq})

            if known:
                alerts.extend(self._observe_known_scanner(mac, distinct, wall, now))
            elif distinct >= self.config.scan_threshold and now >= self._scan_cooldown.get(mac, 0):
                self._scan_cooldown[mac] = now + self.config.cooldown_seconds
                alerts.append(ScanAlert(mac=mac, ip=self._last_ip.get(mac), target_count=distinct, window_seconds=window))

        # --- IP conflict: two MACs claiming the same sender IP close together ---
        # Applies to known scanners too. Requests and gratuitous ARPs both
        # carry the sender's own IP claim.
        if self.config.conflict_enabled and has_ip:
            ip = pkt.sender_ip
            claims = self._claims.setdefault(ip, {})
            claims[mac] = now
            cutoff = now - self.config.conflict_window_seconds
            for other in [m for m, t in claims.items() if t < cutoff]:
                del claims[other]
            if len(claims) > 1 and now >= self._conflict_cooldown.get(ip, 0):
                self._conflict_cooldown[ip] = now + self.config.cooldown_seconds
                alerts.append(ConflictAlert(ip=ip, macs=sorted(claims)))

        return alerts

    # ---------- known scanners: learn, then report only deviations ----------

    def _observe_known_scanner(self, mac: str, distinct: int, wall: float, now: float) -> list[ScanAlert]:
        prof = self.profiles.get(mac)
        if prof is None:
            prof = self.profiles[mac] = ScannerProfile(first_seen=wall)
        hour = int(wall // 3600)
        bucket = prof.hours.setdefault(str(hour), [0, 0, 0])
        bucket[0] += 1
        bucket[1] = max(bucket[1], distinct)

        recent = self._recent.setdefault(mac, deque())
        recent.append(wall)
        while recent and wall - recent[0] > 3600:
            recent.popleft()

        learned = wall - prof.first_seen >= self.config.learning_seconds
        ip = self._last_ip.get(mac)
        reasons: list[str] = []

        if ip and ip not in prof.ips:
            if learned and prof.ips:
                reasons.append(
                    f"skenira sa nove IP adrese {ip} (ranije: {', '.join(prof.ips[-3:])}) — moguće lažno predstavljanje tuđom MAC adresom"
                )
            prof.ips = (prof.ips + [ip])[-5:]

        base = prof.baseline_hours(hour)
        if learned and len(base) >= 2:
            per_hour = sum(v[0] for v in base) / len(base)
            if len(recent) > max(2 * per_hour, per_hour + 300):
                reasons.append(f"{len(recent)} ARP upita u poslednjih sat vremena (uobičajeno ~{per_hour:.0f}/h)")
            usual_max = max(v[1] for v in base)
            if distinct > max(usual_max * 1.5, usual_max + 20):
                reasons.append(
                    f"{distinct} različitih adresa za {self.config.scan_window_seconds}s (uobičajeno najviše {usual_max})"
                )

        if reasons and now >= self._scan_cooldown.get(mac, 0):
            self._scan_cooldown[mac] = now + self.config.cooldown_seconds
            bucket[2] = 1  # an anomalous hour must not become part of "normal"
            return [
                ScanAlert(
                    mac=mac,
                    ip=ip,
                    target_count=distinct,
                    window_seconds=self.config.scan_window_seconds,
                    reason="; ".join(reasons),
                    known_scanner=True,
                )
            ]
        if reasons:
            bucket[2] = 1
        return []

    def tick(self, now: float, wall: float) -> list[ScanAlert]:
        """Periodic housekeeping hook (kept for the sniffer loop)."""
        hour = int(wall // 3600)
        for prof in self.profiles.values():
            prof.prune(hour)
        return []

    def prune(self, now: float) -> None:
        """Bound memory on long-running captures; drop profiles of scanners
        that were removed from the known list."""
        horizon = max(self.config.scan_window_seconds, self.config.conflict_window_seconds)
        for mac in [m for m, dq in self._requests.items() if not dq or now - dq[-1][0] > horizon]:
            del self._requests[mac]
        for ip in [i for i, c in self._claims.items() if not c or now - max(c.values()) > horizon]:
            del self._claims[ip]
        for d in (self._scan_cooldown, self._conflict_cooldown):
            for k in [k for k, until in d.items() if until < now]:
                del d[k]
        for mac in [m for m in self.profiles if m not in self.config.ignore_macs]:
            del self.profiles[mac]
            self._recent.pop(mac, None)
