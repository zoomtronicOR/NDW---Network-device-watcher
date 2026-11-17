from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

_DISCARD_PORT = 9
_DEAD_STATES = {"FAILED", "INCOMPLETE"}


class ScanError(RuntimeError):
    """The scan itself failed (neighbor table unreadable, bad interface...).
    Must never be confused with "the network is empty" -- that used to mark
    every device OFFLINE at once."""


@dataclass
class ScanResult:
    mac: str
    ip: str
    hostname: str | None
    interface: str


class NetworkScanner:
    """ARP/neighbor-table based LAN discovery.

    Uses no raw sockets: sends a throwaway UDP datagram to every host in the
    configured ranges (this alone makes the kernel resolve L2-adjacent
    addresses via ARP as a side effect of routing the packet), waits for
    replies to settle, then reads the resulting state from the kernel
    neighbor table (`ip neigh`). Works unprivileged, including inside
    unprivileged LXC containers that lack CAP_NET_RAW for real ICMP/ARP.
    """

    def __init__(
        self,
        networks: list[str],
        interface: str | None = None,
        settle_seconds: float = 1.5,
        dns_timeout: float = 0.5,
        resolve_hostnames: bool = True,
    ) -> None:
        self.networks = [ipaddress.ip_network(n, strict=False) for n in networks]
        self.interface = interface
        self.settle_seconds = settle_seconds
        self.dns_timeout = dns_timeout
        self.resolve_hostnames = resolve_hostnames

    def scan(self) -> list[ScanResult]:
        local_ips = self._local_ipv4_addresses()
        self._probe_hosts(local_ips)
        time.sleep(self.settle_seconds)
        return self._read_neighbors(local_ips)

    def _probe_hosts(self, local_ips: set[str]) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.interface:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface.encode())
            except OSError:
                pass  # requires CAP_NET_RAW; fall back to default route selection
        for network in self.networks:
            for ip in network.hosts():
                ip_str = str(ip)
                if ip_str in local_ips:
                    continue
                try:
                    sock.sendto(b"\x00", (ip_str, _DISCARD_PORT))
                except OSError:
                    continue
        sock.close()

    def _read_neighbors(self, local_ips: set[str]) -> list[ScanResult]:
        cmd = ["ip", "-j", "neigh", "show"]
        if self.interface:
            cmd += ["dev", self.interface]

        try:
            output = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10).stdout
        except subprocess.CalledProcessError as e:
            raise ScanError(f"`{' '.join(cmd)}` failed: {(e.stderr or '').strip() or e}") from e
        except (subprocess.TimeoutExpired, OSError) as e:
            raise ScanError(f"`{' '.join(cmd)}` failed: {e}") from e

        try:
            entries = json.loads(output or "[]")
        except json.JSONDecodeError as e:
            raise ScanError(f"unparseable `ip neigh` output: {e}") from e

        allowed_ips = {str(ip) for network in self.networks for ip in network.hosts()} - local_ips

        live: list[tuple[str, str, str]] = []
        for entry in entries:
            ip = entry.get("dst", "")
            mac = entry.get("lladdr")
            state = set(entry.get("state", []))
            if not mac or ip not in allowed_ips or state & _DEAD_STATES:
                continue
            live.append((ip, mac.upper(), entry.get("dev") or self.interface or "unknown"))

        hostnames: dict[str, str | None] = {}
        if self.resolve_hostnames and live:
            hostnames = self._resolve_hostnames_bounded([ip for ip, _, _ in live])

        return [
            ScanResult(mac=mac, ip=ip, hostname=hostnames.get(ip), interface=iface) for ip, mac, iface in live
        ]

    def _resolve_hostnames_bounded(self, ips: list[str]) -> dict[str, str | None]:
        # socket.gethostbyaddr() goes through the C library resolver, which does not
        # honor Python's socket timeout -- an overall wall-clock deadline via
        # as_completed() is used instead of a per-call timeout.
        pool = ThreadPoolExecutor(max_workers=32)
        futures = {pool.submit(self._resolve_hostname, ip): ip for ip in ips}
        hostnames: dict[str, str | None] = {}
        try:
            for future in as_completed(futures, timeout=self.dns_timeout * 3):
                hostnames[futures[future]] = future.result()
        except TimeoutError:
            pass  # stragglers left unresolved (None) rather than blocking the scan
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return hostnames

    @staticmethod
    def _resolve_hostname(ip: str) -> str | None:
        try:
            hostname, _, _ = socket.gethostbyaddr(ip)
            return hostname
        except (socket.herror, socket.gaierror, OSError):
            return None

    @staticmethod
    def _local_ipv4_addresses() -> set[str]:
        try:
            output = subprocess.run(
                ["ip", "-j", "-4", "addr", "show"], capture_output=True, text=True, check=True, timeout=5
            ).stdout
            entries = json.loads(output or "[]")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return set()

        addresses = set()
        for entry in entries:
            for addr_info in entry.get("addr_info", []):
                if addr_info.get("family") == "inet":
                    addresses.add(addr_info["local"])
        return addresses
