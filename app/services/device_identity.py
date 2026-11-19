"""Recognizing one physical device behind several MAC addresses.

Phones commonly use a randomized ("private") MAC on one SSID and their real
MAC on another. The DHCP server identifies the client by its client-id /
hostname rather than by MAC, so after an SSID switch both MACs may briefly
hold the same IP -- which looks exactly like an IP conflict but is not one.
"""

from __future__ import annotations

import re

from app.models.device import Device


def _norm(name: str | None) -> str | None:
    if not name:
        return None
    n = re.sub(r"[\s_.]+", "-", name.strip().lower())
    return n or None


def device_hostname_key(device: Device) -> str | None:
    """The DHCP hostname is the device's own self-reported name; fall back to
    the resolved hostname. Manually entered hostnames don't count -- they say
    nothing about the device's identity."""
    if device.dhcp_hostname:
        return _norm(device.dhcp_hostname)
    if device.hostname and not device.hostname_locked:
        return _norm(device.hostname)
    return None


def same_physical_device(devices: list[Device]) -> bool:
    """True when all given MACs report the same (non-empty) hostname."""
    keys = {device_hostname_key(d) for d in devices}
    return len(devices) > 1 and len(keys) == 1 and None not in keys
