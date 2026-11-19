from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.device_event import DeviceEvent
from app.models.enums import ConnectionType, EventType
from app.models.ip_history import IpHistory
from app.services.device_identity import same_physical_device
from app.services.scanner import ScanResult
from app.services.vendor import lookup_vendor


@dataclass
class DetectionSummary:
    # (mac, ip) pairs -- these three have dedicated MQTT/webhook/notification topics
    new_devices: list[tuple[str, str | None]] = field(default_factory=list)
    returned: list[tuple[str, str | None]] = field(default_factory=list)
    went_offline: list[tuple[str, str | None]] = field(default_factory=list)
    ip_changed: list[str] = field(default_factory=list)
    hostname_changed: list[str] = field(default_factory=list)
    vendor_mismatch: list[str] = field(default_factory=list)
    ip_conflicts: list[str] = field(default_factory=list)
    burst_anomaly: bool = False
    suspicious_empty_scan: bool = False


def _connection_type_for_interface(interface: str) -> str:
    return ConnectionType.WIFI.value if interface.lower().startswith("wl") else ConnectionType.LAN.value


class DetectionEngine:
    """Turns raw scan results into device state + device_events, per §7/8/13/30/31.

    MAC address is the identity (§30); IP may legitimately change (DHCP).
    OFFLINE is debounced (§31): a device must be missing for
    `offline_threshold` consecutive scans AND unseen for at least
    `offline_grace_seconds` before it's flagged offline. The scan-count rule
    alone (3 x 30s = 90s) produced thousands of false OFFLINE/RETURNED pairs
    for phones and ESP/Tuya devices whose Wi-Fi power saving skips ARP
    replies for a minute or two.

    `present_macs` (from the Omada controller's associated-client list) also
    counts as "seen" for already-known devices: a sleeping Wi-Fi client that
    is still associated to an AP is present even if it ignored our ARP probe.
    """

    def __init__(
        self,
        db: Session,
        offline_threshold: int = 3,
        burst_threshold: int = 5,
        burst_window_minutes: int = 10,
        offline_grace_seconds: int = 300,
        manage_connection_type: bool = True,
    ) -> None:
        self.db = db
        self.offline_threshold = offline_threshold
        self.offline_grace = timedelta(seconds=max(0, offline_grace_seconds))
        self.conflict_window = timedelta(minutes=10)
        self.conflict_cooldown = timedelta(minutes=10)
        # False when Omada owns LAN/Wi-Fi classification (see omada_client.apply_wifi_clients)
        self.manage_connection_type = manage_connection_type
        self.burst_threshold = burst_threshold
        self.burst_window = timedelta(minutes=burst_window_minutes)

    def process_scan(
        self,
        scan_results: list[ScanResult],
        now: datetime | None = None,
        present_macs: set[str] | None = None,
    ) -> DetectionSummary:
        now = now or datetime.now(timezone.utc)
        summary = DetectionSummary()

        devices_by_mac = {d.mac_address: d for d in self.db.execute(select(Device)).scalars()}

        seen_macs: set[str] = set()
        for result in scan_results:
            seen_macs.add(result.mac)
            self._upsert_device(result, devices_by_mac, now, summary)

        for mac in (present_macs or set()) - seen_macs:
            device = devices_by_mac.get(mac)
            if device is None:
                continue  # unknown MAC without an ARP-confirmed IP: let the ARP scan introduce it
            seen_macs.add(mac)
            self._mark_seen_without_arp(device, now, summary)

        self._flag_ip_conflicts(scan_results, devices_by_mac, now, summary)

        # An ARP scan that sees *nothing* while devices were online is almost
        # certainly a scan problem (wrong interface, link down, ...), not the
        # whole network leaving at once -- don't count it as a miss for anyone.
        online_before = sum(1 for d in devices_by_mac.values() if d.is_online)
        if scan_results or online_before < 3:
            self._mark_missing_offline(devices_by_mac, seen_macs, now, summary)
        else:
            summary.suspicious_empty_scan = True

        if summary.new_devices:
            self._check_burst_anomaly(now, summary)

        self.db.commit()
        return summary

    def _upsert_device(
        self,
        result: ScanResult,
        devices_by_mac: dict[str, Device],
        now: datetime,
        summary: DetectionSummary,
    ) -> None:
        vendor = lookup_vendor(result.mac)
        connection_type = _connection_type_for_interface(result.interface)
        device = devices_by_mac.get(result.mac)

        if device is None:
            device = Device(
                mac_address=result.mac,
                ip_address=result.ip,
                hostname=result.hostname,
                vendor=vendor,
                connection_type=connection_type,
                interface=result.interface,
                first_seen=now,
                last_seen=now,
                is_online=True,
                is_new=True,
                is_trusted=False,
                seen_count=1,
                consecutive_misses=0,
            )
            self.db.add(device)
            self.db.flush()  # assigns device.id for the event/ip_history rows below
            devices_by_mac[result.mac] = device
            self._touch_ip_history(device, result.ip, now)
            self._create_event(device.id, EventType.NEW_DEVICE, result.ip, None, now)
            summary.new_devices.append((device.mac_address, result.ip))
            return

        was_offline = not device.is_online

        device.last_seen = now
        device.seen_count += 1
        device.consecutive_misses = 0
        device.is_online = True
        if self.manage_connection_type or not device.connection_type:
            device.connection_type = connection_type
            device.interface = result.interface

        if was_offline:
            self._create_event(device.id, EventType.DEVICE_RETURNED, result.ip, None, now)
            summary.returned.append((device.mac_address, result.ip))

        if device.ip_address != result.ip:
            details = json.dumps({"old_ip": device.ip_address, "new_ip": result.ip})
            self._create_event(device.id, EventType.IP_CHANGED, result.ip, details, now)
            device.ip_address = result.ip
            summary.ip_changed.append(device.mac_address)

        self._touch_ip_history(device, result.ip, now)

        if result.hostname and result.hostname != device.hostname and not device.hostname_locked:
            if device.hostname:
                details = json.dumps({"old_hostname": device.hostname, "new_hostname": result.hostname})
                self._create_event(device.id, EventType.HOSTNAME_CHANGED, result.ip, details, now)
                summary.hostname_changed.append(device.mac_address)
            device.hostname = result.hostname

        # The OUI vendor is a pure function of the MAC, so for the same MAC it
        # only "changes" when the vendor database itself is updated -- that is
        # not a spoofing signal and must not raise VENDOR_MISMATCH (the real
        # fingerprint check lives in omada_client.apply_omada_clients).
        if vendor and vendor != device.vendor and not device.vendor_locked:
            device.vendor = vendor

    def _mark_missing_offline(
        self,
        devices_by_mac: dict[str, Device],
        seen_macs: set[str],
        now: datetime,
        summary: DetectionSummary,
    ) -> None:
        for mac, device in devices_by_mac.items():
            if mac in seen_macs or not device.is_online:
                continue
            device.consecutive_misses += 1
            unseen_for = now - device.last_seen if device.last_seen else self.offline_grace
            if device.consecutive_misses >= self.offline_threshold and unseen_for >= self.offline_grace:
                device.is_online = False
                self._create_event(device.id, EventType.DEVICE_OFFLINE, device.ip_address, None, now)
                summary.went_offline.append((mac, device.ip_address))

    def _mark_seen_without_arp(self, device: Device, now: datetime, summary: DetectionSummary) -> None:
        was_offline = not device.is_online
        device.last_seen = now
        device.consecutive_misses = 0
        device.is_online = True
        if was_offline:
            self._create_event(device.id, EventType.DEVICE_RETURNED, device.ip_address, None, now)
            summary.returned.append((device.mac_address, device.ip_address))

    def _flag_ip_conflicts(
        self,
        scan_results: list[ScanResult],
        devices_by_mac: dict[str, Device],
        now: datetime,
        summary: DetectionSummary,
    ) -> None:
        """§8.2. The kernel neighbor table holds exactly ONE MAC per
        IP, so a single scan can never show two MACs on one IP (the previous
        "same IP twice in one scan" check could never fire). A conflict shows
        up instead as the IP *flipping* between MACs across scans: device A
        was ARP-seen with IP X within the conflict window and hasn't moved to
        another IP, and now B answers for X. DHCP never hands out an IP whose
        lease is still active, so this is practically always a real conflict
        (typically a static address). The passive ARP sniffer catches the
        same thing from the other side (sniffer_main / arp_monitor).
        """
        owners: dict[str, list[Device]] = {}
        for device in devices_by_mac.values():
            if device.ip_address and device.is_online:
                owners.setdefault(device.ip_address, []).append(device)

        for result in scan_results:
            others = [d for d in owners.get(result.ip, []) if d.mac_address != result.mac]
            recent = []
            for other in others:
                if other.id is None:
                    continue
                seen = self.db.execute(
                    select(IpHistory.last_seen).where(IpHistory.device_id == other.id, IpHistory.ip_address == result.ip)
                ).scalar_one_or_none()
                if seen is not None and seen >= now - self.conflict_window:
                    recent.append(other)
            if not recent or self._conflict_recently_recorded(result.ip, now):
                continue
            claimant = devices_by_mac.get(result.mac)
            if claimant is not None and same_physical_device([claimant, *recent]):
                continue  # one device with several MACs (private/real MAC per SSID), not a conflict

            macs = [result.mac] + [o.mac_address for o in recent]
            for mac in macs:
                device = devices_by_mac.get(mac)
                if device is None or device.id is None:
                    continue
                details = json.dumps({"ip": result.ip, "conflicting_macs": [m for m in macs if m != mac], "source": "scanner"})
                self._create_event(device.id, EventType.IP_CONFLICT, result.ip, details, now)
                summary.ip_conflicts.append(mac)

    def _conflict_recently_recorded(self, ip: str, now: datetime) -> bool:
        # One event per conflicting IP per cooldown: an ongoing conflict keeps
        # the dashboard's "active" (15 min) counter lit without flooding.
        return (
            self.db.execute(
                select(DeviceEvent.id)
                .where(
                    DeviceEvent.event_type == EventType.IP_CONFLICT.value,
                    DeviceEvent.ip_address == ip,
                    DeviceEvent.timestamp >= now - self.conflict_cooldown,
                )
                .limit(1)
            ).first()
            is not None
        )

    def _check_burst_anomaly(self, now: datetime, summary: DetectionSummary) -> None:
        window_start = now - self.burst_window

        recent_new = (
            self.db.execute(
                select(DeviceEvent).where(
                    DeviceEvent.event_type == EventType.NEW_DEVICE.value,
                    DeviceEvent.timestamp >= window_start,
                )
            )
            .scalars()
            .all()
        )
        if len(recent_new) < self.burst_threshold:
            return

        already_flagged = self.db.execute(
            select(DeviceEvent).where(
                DeviceEvent.event_type == EventType.ANOMALY_BURST_NEW_DEVICES.value,
                DeviceEvent.timestamp >= window_start,
            )
        ).scalar()
        if already_flagged:
            return

        anchor = max(recent_new, key=lambda e: e.timestamp)
        details = json.dumps(
            {
                "count": len(recent_new),
                "window_minutes": self.burst_window.total_seconds() / 60,
                "device_ids": [e.device_id for e in recent_new],
            }
        )
        self._create_event(anchor.device_id, EventType.ANOMALY_BURST_NEW_DEVICES, None, details, now)
        summary.burst_anomaly = True

    def _touch_ip_history(self, device: Device, ip: str, now: datetime) -> None:
        entry = self.db.execute(
            select(IpHistory).where(IpHistory.device_id == device.id, IpHistory.ip_address == ip)
        ).scalar_one_or_none()
        if entry:
            entry.last_seen = now
        else:
            self.db.add(IpHistory(device_id=device.id, ip_address=ip, first_seen=now, last_seen=now))

    def _create_event(
        self,
        device_id: int,
        event_type: EventType,
        ip_address: str | None,
        details: str | None,
        now: datetime,
    ) -> None:
        self.db.add(
            DeviceEvent(
                device_id=device_id,
                event_type=event_type.value,
                ip_address=ip_address,
                timestamp=now,
                details=details,
            )
        )
