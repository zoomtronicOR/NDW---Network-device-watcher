"""Device-inventory backup (§33): export the `devices` table to XLSX/CSV/PDF and
import it back from XLSX/CSV.

Only the device inventory is covered - no events, IP history, ping results or
statistics. XLSX/CSV use the raw column names below so the file round-trips
losslessly; the plain Devices-page export (Status/IP/MAC/... headers) is also
accepted on import via _HEADER_ALIASES. PDF is a read-only report.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.device_event import DeviceEvent

# Persistent device data. Runtime state (is_online/is_new/consecutive_misses)
# is deliberately left out - it is re-established by the scanner.
_STR_FIELDS = {
    "ip_address": 45,
    "ipv6_address": 45,
    "hostname": 255,
    "dhcp_hostname": 255,
    "mdns_hostname": 255,
    "netbios_hostname": 255,
    "vendor": 255,
    "device_type": 100,
    "connection_type": 10,
    "interface": 50,
    "wifi_ssid": 255,
    "gateway": 45,
    "switch_port": 50,
    "os_fingerprint": 255,
    "custom_name": 255,
    "notes": None,
}
_INT_FIELDS = {"wifi_rssi", "vlan", "seen_count"}
_BOOL_FIELDS = {"is_trusted", "hostname_locked", "vendor_locked", "device_type_auto"}
_DT_FIELDS = {"first_seen", "last_seen"}

FIELDS = [
    "mac_address",
    "ip_address",
    "ipv6_address",
    "hostname",
    "dhcp_hostname",
    "mdns_hostname",
    "netbios_hostname",
    "vendor",
    "device_type",
    "connection_type",
    "interface",
    "wifi_ssid",
    "wifi_rssi",
    "gateway",
    "vlan",
    "switch_port",
    "os_fingerprint",
    "first_seen",
    "last_seen",
    "seen_count",
    "is_trusted",
    "hostname_locked",
    "vendor_locked",
    "device_type_auto",
    "custom_name",
    "notes",
]

# Headers of the regular Devices-page Excel/CSV export (§22), lowercased.
_HEADER_ALIASES = {
    "mac": "mac_address",
    "ip": "ip_address",
    "connection": "connection_type",
    "first seen": "first_seen",
    "last seen": "last_seen",
    "name": "custom_name",
}
_IGNORED_HEADERS = {"status"}

_MAC_RE = re.compile(r"^([0-9A-F]{2}[:-]){5}[0-9A-F]{2}$")
_MAC_BARE_RE = re.compile(r"^[0-9A-F]{12}$")
_TRUE = {"1", "true", "yes", "da", "y", "x"}
_FALSE = {"0", "false", "no", "ne", "n", ""}
MAX_ERRORS_SHOWN = 20


class BackupFormatError(ValueError):
    pass


# ---------------------------------------------------------------- export


def _cell_value(device: Device, name: str):
    value = getattr(device, name)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat(timespec="seconds")
    return value


def build_devices_xlsx(devices: list[Device]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Devices"
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0E7490", end_color="0E7490", fill_type="solid")
    for col, name in enumerate(FIELDS, start=1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left")
        ws.column_dimensions[get_column_letter(col)].width = max(12, min(32, len(name) + 4))
    for row, device in enumerate(devices, start=2):
        for col, name in enumerate(FIELDS, start=1):
            ws.cell(row=row, column=col, value=_cell_value(device, name))
    ws.auto_filter.ref = f"A1:{get_column_letter(len(FIELDS))}{len(devices) + 1}"
    ws.freeze_panes = "B2"

    meta = wb.create_sheet("Info")
    meta.append(["format", "networkwatcher-devices"])
    meta.append(["version", 1])
    meta.append(["exported_at", datetime.now(timezone.utc).isoformat(timespec="seconds")])
    meta.append(["devices", len(devices)])

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_devices_csv(devices: list[Device]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    for device in devices:
        writer.writerow(["" if (v := _cell_value(device, n)) is None else v for n in FIELDS])
    return buffer.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------- parsing


def _read_table(filename: str, raw: bytes) -> list[list]:
    name = (filename or "").lower()
    if name.endswith(".xlsx") or raw[:2] == b"PK":
        try:
            wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001 - any openpyxl failure means "bad file"
            raise BackupFormatError(f"Fajl nije ispravan .xlsx: {e}") from None
        ws = wb["Devices"] if "Devices" in wb.sheetnames else wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    if name.endswith(".csv") or not name:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1250", errors="replace")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return [row for row in csv.reader(io.StringIO(text), dialect)]
    raise BackupFormatError("Podržani formati za uvoz su .xlsx i .csv (PDF služi samo za pregled).")


def _map_headers(header: list) -> list[str | None]:
    mapped: list[str | None] = []
    for h in header:
        key = str(h).strip().lower() if h is not None else ""
        if key in FIELDS:
            mapped.append(key)
        elif key in _HEADER_ALIASES:
            mapped.append(_HEADER_ALIASES[key])
        elif key.replace(" ", "_") in FIELDS:
            mapped.append(key.replace(" ", "_"))
        else:
            mapped.append(None)
    return mapped


def _norm_mac(value) -> str:
    mac = str(value or "").strip().upper()
    if _MAC_BARE_RE.match(mac):
        mac = ":".join(mac[i : i + 2] for i in range(0, 12, 2))
    if not _MAC_RE.match(mac):
        raise ValueError(f"neispravna MAC adresa '{value}'")
    return mac.replace("-", ":")


def _parse_dt(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"neispravan datum '{value}'") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_value(name: str, value):
    if name in _DT_FIELDS:
        return _parse_dt(value)
    if name in _BOOL_FIELDS:
        if isinstance(value, bool):
            return value
        text = str(value if value is not None else "").strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ValueError(f"{name}: neispravna logička vrednost '{value}'")
    if name in _INT_FIELDS:
        if value is None or str(value).strip() == "":
            return None
        try:
            return int(float(str(value).strip()))
        except ValueError:
            raise ValueError(f"{name}: nije ceo broj '{value}'") from None
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    limit = _STR_FIELDS.get(name)
    return text[:limit] if limit else text


@dataclass
class ParsedBackup:
    rows: list[dict] = field(default_factory=list)  # each has mac_address + parsed columns
    columns: list[str] = field(default_factory=list)  # fields present in the file
    errors: list[str] = field(default_factory=list)
    error_count: int = 0


def parse_backup(filename: str, raw: bytes) -> ParsedBackup:
    table = [r for r in _read_table(filename, raw) if any(c not in (None, "") for c in r)]
    if not table:
        raise BackupFormatError("Fajl je prazan.")
    headers = _map_headers(table[0])
    if "mac_address" not in headers:
        raise BackupFormatError("Fajl nema kolonu 'mac_address' (ili 'MAC') - nije backup uređaja.")

    result = ParsedBackup(columns=[h for h in dict.fromkeys(headers) if h])
    seen: dict[str, int] = {}
    for line_no, row in enumerate(table[1:], start=2):
        try:
            item: dict = {}
            for idx, name in enumerate(headers):
                if not name:
                    continue
                value = row[idx] if idx < len(row) else None
                item[name] = _norm_mac(value) if name == "mac_address" else _parse_value(name, value)
            mac = item["mac_address"]
            if mac in seen:
                raise ValueError(f"MAC {mac} se ponavlja (prvi put u redu {seen[mac]})")
            seen[mac] = line_no
            result.rows.append(item)
        except ValueError as e:
            result.error_count += 1
            if len(result.errors) < MAX_ERRORS_SHOWN:
                result.errors.append(f"Red {line_no}: {e}")
    return result


# ---------------------------------------------------------------- import


@dataclass
class ImportPlan:
    mode: str
    total_rows: int
    invalid_rows: int
    errors: list[str]
    columns: list[str]
    to_create: int
    to_update: int
    unchanged: int
    to_delete: int  # replace mode: devices removed from the DB
    events_lost: int  # replace mode: device_events rows removed with them
    destructive: bool


def _merged_values(device: Device, item: dict) -> dict:
    """Values the import would write to an existing device (merge mode)."""
    out = {}
    for name, value in item.items():
        if name == "mac_address":
            continue
        current = getattr(device, name)
        if name in _DT_FIELDS and value and current and abs((value - current).total_seconds()) < 1:
            continue  # export is second-precision; DB keeps microseconds
        if name == "first_seen" and value and current:
            value = min(value, current)
        elif name == "last_seen" and value and current:
            value = max(value, current)
        elif name == "seen_count" and value is not None and current is not None:
            value = max(value, current)
        if name in _DT_FIELDS and value is None:
            continue  # NOT NULL columns
        if name in _BOOL_FIELDS | {"seen_count"} and value is None:
            continue
        if value != current:
            out[name] = value
    return out


def plan_import(db: Session, parsed: ParsedBackup, mode: str) -> ImportPlan:
    if mode not in ("merge", "replace"):
        raise BackupFormatError("Nepoznat režim uvoza.")
    existing = {d.mac_address: d for d in db.execute(select(Device)).scalars()}
    to_create = to_update = unchanged = 0
    if mode == "replace":
        to_create = len(parsed.rows)
    else:
        for item in parsed.rows:
            device = existing.get(item["mac_address"])
            if device is None:
                to_create += 1
            elif _merged_values(device, item):
                to_update += 1
            else:
                unchanged += 1
    to_delete = len(existing) if mode == "replace" else 0
    events_lost = (
        db.execute(select(func.count()).select_from(DeviceEvent)).scalar_one() if mode == "replace" else 0
    )
    return ImportPlan(
        mode=mode,
        total_rows=len(parsed.rows) + parsed.error_count,
        invalid_rows=parsed.error_count,
        errors=parsed.errors,
        columns=parsed.columns,
        to_create=to_create,
        to_update=to_update,
        unchanged=unchanged,
        to_delete=to_delete,
        events_lost=events_lost,
        destructive=bool(to_update or to_delete),
    )


def _new_device(item: dict) -> Device:
    now = datetime.now(timezone.utc)
    values = {k: v for k, v in item.items() if v is not None}
    values.setdefault("first_seen", values.get("last_seen", now))
    values.setdefault("last_seen", values["first_seen"])
    values.setdefault("seen_count", 1)
    # Imported devices start offline and not-new; the scanner flips them to
    # ONLINE (DEVICE_RETURNED) the first time it sees them.
    return Device(**values, is_online=False, is_new=False, consecutive_misses=0)


def apply_import(db: Session, parsed: ParsedBackup, mode: str) -> ImportPlan:
    plan = plan_import(db, parsed, mode)
    if mode == "replace":
        db.query(Device).delete(synchronize_session=False)
        db.flush()
        for item in parsed.rows:
            db.add(_new_device(item))
    else:
        existing = {d.mac_address: d for d in db.execute(select(Device)).scalars()}
        for item in parsed.rows:
            device = existing.get(item["mac_address"])
            if device is None:
                db.add(_new_device(item))
                continue
            for name, value in _merged_values(device, item).items():
                setattr(device, name, value)
    db.commit()
    return plan
