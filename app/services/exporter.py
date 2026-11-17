from __future__ import annotations

import csv
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.models.device import Device
from app.schemas.device import compute_status

# §22: Status, IP, MAC, hostname, vendor, connection type,
# first seen, last seen, custom name, notes.
_COLUMNS = [
    ("Status", 12),
    ("IP", 16),
    ("MAC", 18),
    ("Hostname", 24),
    ("Vendor", 28),
    ("Connection", 12),
    ("First seen", 20),
    ("Last seen", 20),
    ("Name", 22),
    ("Notes", 32),
]


def _local_naive(dt: datetime) -> datetime:
    return dt.astimezone().replace(tzinfo=None)


def _row_values(device: Device) -> list:
    return [
        compute_status(device),
        device.ip_address or "",
        device.mac_address,
        device.hostname or "",
        device.vendor or "",
        device.connection_type or "",
        _local_naive(device.first_seen),
        _local_naive(device.last_seen),
        device.custom_name or "",
        device.notes or "",
    ]


def build_excel_export(devices: list[Device]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Devices"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0E7490", end_color="0E7490", fill_type="solid")

    for col_idx, (label, width) in enumerate(_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left")
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    for row_idx, device in enumerate(devices, start=2):
        for col_idx, value in enumerate(_row_values(device), start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if isinstance(value, datetime):
                cell.number_format = "DD.MM.YYYY HH:MM:SS"

    last_col = get_column_letter(len(_COLUMNS))
    ws.auto_filter.ref = f"A1:{last_col}{len(devices) + 1}"
    ws.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_csv_export(devices: list[Device]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for label, _ in _COLUMNS])
    for device in devices:
        row = [v.strftime("%d.%m.%Y %H:%M:%S") if isinstance(v, datetime) else v for v in _row_values(device)]
        writer.writerow(row)
    return buffer.getvalue()
