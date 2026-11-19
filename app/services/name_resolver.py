"""NetBIOS and mDNS name lookups for single hosts (no privileges, stdlib only).

* NetBIOS: a Node Status (NBSTAT) request to UDP 137 of the host. Answered by
  Windows machines, Samba (NAS, Linux) and many printers.
* mDNS: a reverse PTR query ("x.y.z.w.in-addr.arpa") sent by unicast to the
  host's UDP 5353. Responders treat it as a "legacy unicast" query and reply
  to our source port with their `<name>.local`. Answered by Apple devices,
  Chromecast/Google, printers, ESPHome, Avahi/Linux and some Android devices.

Both return None on timeout / no answer -- most devices simply don't run
these services, which is normal.
"""

from __future__ import annotations

import random
import socket
import struct

NETBIOS_PORT = 137
MDNS_PORT = 5353


# ---------------- NetBIOS ----------------

def _netbios_encode(name: str) -> bytes:
    """First-level NetBIOS name encoding of a 16-byte name ('*' padded with NULs)."""
    raw = name.encode("ascii").ljust(16, b"\x00")[:16]
    encoded = bytearray()
    for b in raw:
        encoded.append(ord("A") + (b >> 4))
        encoded.append(ord("A") + (b & 0x0F))
    return bytes([32]) + bytes(encoded) + b"\x00"


def netbios_name(ip: str, timeout: float = 0.8) -> str | None:
    tid = random.randint(0, 0xFFFF)
    # header: id, flags=0, qd=1, an=0, ns=0, ar=0; question: '*' NBSTAT(0x21) IN(1)
    packet = struct.pack(">HHHHHH", tid, 0, 1, 0, 0, 0) + _netbios_encode("*") + struct.pack(">HH", 0x21, 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(packet, (ip, NETBIOS_PORT))
        data, _ = sock.recvfrom(2048)
    except OSError:
        return None
    finally:
        sock.close()
    try:
        if len(data) < 57 or struct.unpack(">H", data[:2])[0] != tid:
            return None
        pos = 12
        # answer name: either a pointer (2 bytes) or a full encoded name
        if data[pos] & 0xC0 == 0xC0:
            pos += 2
        else:
            while data[pos] != 0:
                pos += data[pos] + 1
            pos += 1
        pos += 2 + 2 + 4  # type, class, ttl
        pos += 2  # rdlength
        count = data[pos]
        pos += 1
        names = []
        for _ in range(count):
            entry = data[pos : pos + 18]
            if len(entry) < 18:
                break
            name = entry[:15].decode("ascii", errors="replace").strip()
            suffix = entry[15]
            flags = struct.unpack(">H", entry[16:18])[0]
            names.append((name, suffix, bool(flags & 0x8000)))
            pos += 18
    except (IndexError, struct.error):
        return None
    # the workstation name: unique (not group) entry with suffix 0x00
    for name, suffix, is_group in names:
        if suffix == 0x00 and not is_group and name:
            return name
    for name, _suffix, is_group in names:
        if not is_group and name:
            return name
    return None


# ---------------- mDNS ----------------

def _dns_name(labels: list[str]) -> bytes:
    out = b""
    for label in labels:
        raw = label.encode("utf-8")
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def _read_name(data: bytes, pos: int, depth: int = 0) -> tuple[str, int]:
    """Decode a (possibly compressed) DNS name; returns (name, next position)."""
    labels = []
    jumped_end = None
    while True:
        if depth > 10 or pos >= len(data):
            raise ValueError("bad name")
        length = data[pos]
        if length == 0:
            pos += 1
            break
        if length & 0xC0 == 0xC0:
            pointer = struct.unpack(">H", data[pos : pos + 2])[0] & 0x3FFF
            if jumped_end is None:
                jumped_end = pos + 2
            name, _ = _read_name(data, pointer, depth + 1)
            if name:
                labels.append(name)
            pos = jumped_end
            return ".".join(labels), pos
        pos += 1
        labels.append(data[pos : pos + length].decode("utf-8", errors="replace"))
        pos += length
    return ".".join(labels), (jumped_end if jumped_end is not None else pos)


def mdns_name(ip: str, timeout: float = 1.0) -> str | None:
    tid = random.randint(0, 0xFFFF)
    reverse = list(reversed(ip.split("."))) + ["in-addr", "arpa"]
    packet = struct.pack(">HHHHHH", tid, 0, 1, 0, 0, 0) + _dns_name(reverse) + struct.pack(">HH", 12, 1)  # PTR IN
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(packet, (ip, MDNS_PORT))
        data, addr = sock.recvfrom(9000)
    except OSError:
        return None
    finally:
        sock.close()
    try:
        if addr[0] != ip or len(data) < 12:
            return None
        _tid, flags, qd, an, _ns, _ar = struct.unpack(">HHHHHH", data[:12])
        if not flags & 0x8000 or an == 0:
            return None
        pos = 12
        for _ in range(qd):
            _, pos = _read_name(data, pos)
            pos += 4
        for _ in range(an):
            _, pos = _read_name(data, pos)
            rtype, _rclass, _ttl, rdlen = struct.unpack(">HHIH", data[pos : pos + 10])
            pos += 10
            if rtype == 12:  # PTR
                target, _ = _read_name(data, pos)
                return target.rstrip(".") or None
            pos += rdlen
    except (ValueError, IndexError, struct.error):
        return None
    return None


def short_mdns(name: str | None) -> str | None:
    """'Living-Room.local' -> 'Living-Room' (for use as a hostname)."""
    if not name:
        return None
    return name[:-6] if name.lower().endswith(".local") else name
