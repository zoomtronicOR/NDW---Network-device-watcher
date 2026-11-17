from __future__ import annotations

import io
import logging
from datetime import datetime

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Circle, Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.device import Device
from app.schemas.device import compute_status

logger = logging.getLogger("networkwatcher.pdf")

_PRIMARY = colors.HexColor("#0E7490")
_ROW_ALT = colors.HexColor("#F1F5F9")
_MUTED = colors.HexColor("#64748B")

# Base-14 PDF fonts (Helvetica) lack Serbian Latin diacritics (š, đ, č, ć, ž).
# DejaVu Sans covers them; fall back to Helvetica if the font isn't installed
# rather than failing the export outright.
_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    _FONT_REGULAR = "DejaVuSans"
    _FONT_BOLD = "DejaVuSans-Bold"
except Exception:
    logger.warning("DejaVu Sans not found; PDF export will fall back to Helvetica (no Serbian diacritics)")


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(_FONT_REGULAR, 7)
    canvas.setFillColor(_MUTED)
    canvas.drawRightString(doc.pagesize[0] - 1.5 * cm, 1 * cm, f"Strana {doc.page}")
    canvas.drawString(1.5 * cm, 1 * cm, "Network Device Watcher")
    canvas.restoreState()


def _new_devices_chart(daily_new: list[dict], width: float = 750, height: float = 160) -> Drawing:
    dates = [p["date"] for p in daily_new]
    values = [p["count"] for p in daily_new]

    drawing = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x = 35
    chart.y = 30
    chart.width = width - 55
    chart.height = height - 50
    chart.data = [values]
    chart.bars[0].fillColor = _PRIMARY
    chart.bars[0].strokeColor = None
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 7
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 90
    chart.categoryAxis.labels.dx = -3
    chart.categoryAxis.labels.dy = -18
    chart.categoryAxis.labels.boxAnchor = "e"

    # Thin out category labels so they don't overlap on longer periods --
    # every bar still renders, only some get a date label underneath.
    show_every = max(1, len(dates) // 20)
    chart.categoryAxis.categoryNames = [d if i % show_every == 0 else "" for i, d in enumerate(dates)]

    drawing.add(chart)
    return drawing


def _logo_drawing(size: float = 16) -> Drawing:
    """Small filled dot echoing the web app header's `.dot` mark next to the
    title -- stands in for an uploaded logo (§23, optional)
    since the app has no branding image asset to embed.
    """
    d = Drawing(size, size)
    d.add(Circle(size / 2, size / 2, size / 2, fillColor=_PRIMARY, strokeColor=None))
    return d


def build_pdf_report(
    devices: list[Device],
    *,
    period_days: int | None = None,
    daily_new: list[dict] | None = None,
) -> bytes:
    """§23: app name, generation date, total/online/offline
    counts, and the device table are required. The optional extras (logo,
    extra statistics, a chart, report period) are included when the caller
    supplies them: pass `period_days` + `daily_new` (from the same query as
    `/api/charts/new-devices-daily`) to add a "Period izveštaja" line and a
    bar chart of new devices per day; omit both for the minimal report.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title="Network Device Watcher - Izveštaj",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleNW", parent=styles["Title"], textColor=_PRIMARY, fontSize=20, fontName=_FONT_BOLD
    )
    meta_style = ParagraphStyle("MetaNW", parent=styles["Normal"], textColor=_MUTED, fontName=_FONT_REGULAR)
    stat_label_style = ParagraphStyle(
        "StatLabel", parent=styles["Normal"], fontSize=8, textColor=_MUTED, fontName=_FONT_REGULAR
    )
    stat_value_style = ParagraphStyle(
        "StatValue", parent=styles["Normal"], fontSize=16, textColor=_PRIMARY, leading=20, fontName=_FONT_BOLD
    )

    title_row = Table(
        [[_logo_drawing(), Paragraph("Network Device Watcher", title_style)]],
        colWidths=[1 * cm, None],
    )
    title_row.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])
    )

    period_label = "Period: svi podaci" if period_days is None else f"Period: poslednjih {period_days} dana"

    elements = [
        title_row,
        Paragraph("Izveštaj o uređajima na mreži", meta_style),
        Paragraph(f"Generisano: {datetime.now().astimezone().strftime('%d.%m.%Y %H:%M:%S')}", meta_style),
        Paragraph(period_label, meta_style),
        Spacer(1, 0.5 * cm),
    ]

    total = len(devices)
    online = sum(1 for d in devices if d.is_online)
    stat_cells = [
        ("Ukupno uređaja", total),
        ("Online", online),
        ("Offline", total - online),
        ("Novih", sum(1 for d in devices if d.is_new)),
        ("Wi-Fi", sum(1 for d in devices if d.connection_type == "WIFI")),
        ("LAN", sum(1 for d in devices if d.connection_type == "LAN")),
        ("Poverljivi", sum(1 for d in devices if d.is_trusted)),
    ]
    stat_table = Table(
        [
            [Paragraph(label, stat_label_style) for label, _ in stat_cells],
            [Paragraph(str(value), stat_value_style) for _, value in stat_cells],
        ],
        colWidths=[3.6 * cm] * len(stat_cells),
    )
    stat_table.setStyle(
        TableStyle(
            [
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#CBD5E1")),
            ]
        )
    )
    elements.append(stat_table)
    elements.append(Spacer(1, 0.7 * cm))

    if daily_new:
        elements.append(Paragraph("Novi uređaji po danu", stat_label_style))
        elements.append(Spacer(1, 0.2 * cm))
        elements.append(_new_devices_chart(daily_new))
        elements.append(Spacer(1, 0.7 * cm))

    header = ["Status", "MAC", "IP", "Hostname", "Vendor", "Veza", "Prvi put viđen", "Poslednji put viđen", "Naziv"]
    table_data = [header]
    for d in devices:
        table_data.append(
            [
                compute_status(d),
                d.mac_address,
                d.ip_address or "-",
                d.hostname or "-",
                (d.vendor or "-")[:28],
                d.connection_type or "-",
                d.first_seen.astimezone().strftime("%d.%m.%Y %H:%M"),
                d.last_seen.astimezone().strftime("%d.%m.%Y %H:%M"),
                d.custom_name or "-",
            ]
        )

    col_widths = [1.8 * cm, 3.2 * cm, 2.8 * cm, 3.0 * cm, 4.0 * cm, 1.6 * cm, 3.2 * cm, 3.2 * cm, 3.0 * cm]
    device_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), _PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 1), (-1, -1), _FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for row_idx in range(1, len(table_data)):
        if row_idx % 2 == 0:
            style_commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), _ROW_ALT))
    device_table.setStyle(TableStyle(style_commands))
    elements.append(device_table)

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
