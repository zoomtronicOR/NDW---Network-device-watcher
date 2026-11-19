"""Best-effort automatic device type (§24: icons per device_type).

Only fills/refines device_type for devices whose type is empty or was set by
this classifier (device_type_auto=True) -- a type the user typed is never
touched. Uses the same labels the user already uses (IOT, Telefon, Camera,
Server, ...). Signals, strongest first: Omada infrastructure device lists
(AP / switch / gateway), the default gateway IP, hostname keywords, vendor
keywords, and Omada's own client fingerprint. Returns None when unsure --
"Nepoznato" is better than a confident wrong guess (§6).
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from app.services.vendor import is_locally_administered

# (label, hostname regex) -- checked in order, first match wins.
_HOSTNAME_RULES: list[tuple[str, str]] = [
    ("Router", r"\b(router|gateway|mikrotik|routerboard|openwrt|fritz\W?box|pfsense|opnsense)\b"),
    ("Access point", r"\b(eap\d*|unifi|uap|access\W?point|ap\d+)\b"),
    ("Switch", r"\bswitch\b"),
    ("Kamera", r"(\bcam\b|camera|kamera|\bipc\b|hikvision|dahua|reolink|imou|ezviz|tapo\W?c\d|wyze|doorbell|zvono)"),
    ("Smart Watch", r"(watch|\bband\b|fitbit|garmin)"),
    ("Telefon", r"(iphone|android|galaxy|pixel|redmi|poco|oneplus|huawei|honor|motorola|\bmoto\b|xiaomi\W?1\d|nokia|\bsm-[a-z]\d|\bs2\dfe|\bs2\d)"),
    ("Tablet", r"(ipad|tablet|\btab\b|galaxy\W?tab|lenovo\W?tab|kindle)"),
    ("Laptop", r"(laptop|macbook|notebook|thinkpad|\bxps\b|zenbook|vivobook|ideapad|surface)"),
    ("TV Box", r"(chromecast|mibox|mi\W?box|shield|fire\W?tv|firetv|roku|apple\W?tv|android\W?tv\W?box|\bstb\b|formuler|mag\d{3})"),
    ("TV", r"(\btv\b|bravia|webos|tizen|smart\W?tv|\blgwebostv|samsung\W?tv|philips\W?tv|hisense|tcl)"),
    ("Štampač", r"(printer|stampac|štampač|\bnpi[0-9a-f]{6}|\bbrn[0-9a-f]{6}|epson|canon|laserjet|officejet|deskjet)"),
    ("Konzola", r"(playstation|\bps[45]\b|xbox|nintendo|switch\W?console|steam\W?deck)"),
    ("NAS", r"(\bnas\b|diskstation|synology|qnap|truenas|unraid|openmediavault|\bomv\b)"),
    ("Server", r"(proxmox|\bpve\b|server|\bsrv\b|docker|\blxc\b|esxi|hyper-?v|ubuntu|debian)"),
    ("Computer", r"(desktop-|\bpc\b|workstation|\bimac\b|mac\W?mini|win-[a-z0-9]{6,})"),
    ("IOT", r"(rt-?thread|freertos|lwip|\bwlan0\b|beken|bk72\d\d|hf-lpb|\bty[_-]|esp[_-]?\w{4,}|esp32|esp8266|espressif|tasmota|shelly|sonoff|tuya|\bwled\b|zigbee|tradfri|hue|\bplug\b|utičnica|sijalica|bulb|\bled\b|nest|google-home|echo|alexa|sensor|senzor|thermostat|termostat|vacuum|usisivac|robot|roborock|dreame|\bmiio\b|yeelight|broadlink|meross|\bcam\b)"),
]

# (label, vendor regex) -- weaker than hostname.
_VENDOR_RULES: list[tuple[str, str]] = [
    ("Router", r"(routerboard|mikrotik|ubiquiti.*gateway|netgate|avm gmbh)"),
    ("Kamera", r"(hikvision|dahua|reolink|zhen shi information|imilab|tianjin hualai|shenzhen bilian|vstarcam|uniview|axis comm)"),
    ("NAS", r"(synology|qnap|western digital|buffalo)"),
    ("Server", r"(proxmox|supermicro|vmware|xensource|microsoft corporation.*hyper)"),
    ("Štampač", r"(brother industries|seiko epson|canon inc|kyocera|lexmark|xerox|ricoh)"),
    ("Konzola", r"(sony interactive|nintendo)"),
    ("TV", r"(lg electronics|samsung electronics.*visual|tcl king|hisense|vizio|sharp corp|panasonic.*av)"),
    ("IOT", r"(espressif|tuya|shelly|allterco|itead|sonoff|signify|philips lighting|lumi united|aqara|beijing xiaomi|xiaomi communications|yeelight|broadlink|meross|wiz connected|nanoleaf|gaoshengda|hui zhou|ezviz|ecovacs|roborock|dreame|google, inc|amazon technologies|sonos|tp-link.*tapo)"),
    ("Telefon", r"(apple, inc|samsung electronics|oneplus|motorola mobility|huawei device|honor device|vivo mobile|oppo|realme|guangdong oppo|xiaomi.*mobile)"),
    ("Computer", r"(intel corporate|giga-byte|asustek|micro-star|dell inc|hewlett packard|lenovo)"),
]

# Omada's own client fingerprint (deviceCategory / deviceType) when not "Unknown".
_OMADA_CATEGORY = {
    "phone": "Telefon",
    "mobile": "Telefon",
    "pad": "Tablet",
    "tablet": "Tablet",
    "pc": "Computer",
    "computer": "Computer",
    "laptop": "Laptop",
    "tv": "TV",
    "camera": "Kamera",
    "printer": "Štampač",
    "iot": "IOT",
    "smart home": "IOT",
    "game": "Konzola",
    "nas": "NAS",
    "server": "Server",
}

# Existing user vocabulary uses English "Camera"; keep that spelling so the
# donut chart doesn't split one category into two.
_ALIASES = {"Kamera": "Camera"}


@dataclass
class ClassifyInput:
    mac: str
    vendor: str | None
    hostname: str | None
    dhcp_hostname: str | None
    ip: str | None
    connection_type: str | None
    omada_client: dict | None = None
    omada_infra_type: str | None = None  # "ap" / "switch" / "gateway"
    gateway_ip: str | None = None


def default_gateway_ip() -> str | None:
    try:
        out = subprocess.run(["ip", "-j", "-4", "route", "show", "default"], capture_output=True, text=True, timeout=5).stdout
        routes = json.loads(out or "[]")
        return routes[0].get("gateway") if routes else None
    except Exception:
        return None


def _match(rules: list[tuple[str, str]], text: str | None) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for label, pattern in rules:
        if re.search(pattern, lowered):
            return label
    return None


def classify(inp: ClassifyInput) -> str | None:
    label = _classify(inp)
    return _ALIASES.get(label, label) if label else None


def _classify(inp: ClassifyInput) -> str | None:
    infra = {"ap": "Access point", "switch": "Switch", "gateway": "Router"}.get((inp.omada_infra_type or "").lower())
    if infra:
        return infra
    if inp.gateway_ip and inp.ip == inp.gateway_ip:
        return "Router"

    for name in (inp.hostname, inp.dhcp_hostname):
        found = _match(_HOSTNAME_RULES, name)
        if found:
            return found

    if inp.omada_client:
        for key in ("deviceCategory", "deviceType"):
            value = str(inp.omada_client.get(key) or "").strip().lower()
            if value and value not in ("unknown", "others", "other"):
                for k, lbl in _OMADA_CATEGORY.items():
                    if k in value:
                        return lbl

    found = _match(_VENDOR_RULES, inp.vendor)
    if found:
        # Apple/Samsung also make laptops/TVs/tablets; without a hostname hint,
        # only call it a phone when it's on Wi-Fi.
        if found == "Telefon" and (inp.connection_type or "").upper() != "WIFI":
            return None
        return found

    # A private (randomized) MAC on Wi-Fi with nothing else to go on is almost
    # always a phone/tablet; on a wire it's usually a VM/container -- unsure.
    if is_locally_administered(inp.mac) and (inp.connection_type or "").upper() == "WIFI":
        return "Telefon"
    return None


def apply_classification(db, omada_clients: dict | None, infra: dict | None) -> int:
    """Fill/refine device_type for devices with no type or an auto type.
    Returns how many devices changed. Never touches a user-set type."""
    from sqlalchemy import or_, select

    from app.models.device import Device

    gateway = default_gateway_ip()
    devices = (
        db.execute(select(Device).where(or_(Device.device_type.is_(None), Device.device_type_auto.is_(True))))
        .scalars()
        .all()
    )
    changed = 0
    for d in devices:
        label = classify(
            ClassifyInput(
                mac=d.mac_address,
                vendor=d.vendor,
                hostname=d.hostname,
                dhcp_hostname=d.dhcp_hostname or d.mdns_hostname or d.netbios_hostname,
                ip=d.ip_address,
                connection_type=d.connection_type,
                omada_client=(omada_clients or {}).get(d.mac_address),
                omada_infra_type=((infra or {}).get(d.mac_address) or {}).get("type"),
                gateway_ip=gateway,
            )
        )
        if label and label != d.device_type:
            d.device_type = label
            d.device_type_auto = True
            changed += 1
    if changed:
        db.commit()
    return changed
