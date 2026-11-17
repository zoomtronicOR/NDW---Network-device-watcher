from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.device import Device
from app.models.device_event import DeviceEvent
from app.models.enums import EventType
from app.services.exporter import build_csv_export, build_excel_export
from app.services.pdf_report import build_pdf_report

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/excel")
def export_excel(db: Session = Depends(get_db)) -> Response:
    devices = db.execute(select(Device).order_by(Device.mac_address)).scalars().all()
    content = build_excel_export(devices)
    filename = f"networkwatcher-devices-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pdf")
def export_pdf(days: int | None = None, db: Session = Depends(get_db)) -> Response:
    devices = db.execute(select(Device).order_by(Device.mac_address)).scalars().all()

    daily_new = None
    if days:
        window_start = datetime.now(timezone.utc) - timedelta(days=days)
        rows = db.execute(
            select(func.date(DeviceEvent.timestamp), func.count())
            .where(DeviceEvent.event_type == EventType.NEW_DEVICE.value, DeviceEvent.timestamp >= window_start)
            .group_by(func.date(DeviceEvent.timestamp))
            .order_by(func.date(DeviceEvent.timestamp))
        ).all()
        daily_new = [{"date": str(d), "count": c} for d, c in rows]

    content = build_pdf_report(devices, period_days=days, daily_new=daily_new)
    filename = f"networkwatcher-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/csv")
def export_csv(db: Session = Depends(get_db)) -> Response:
    devices = db.execute(select(Device).order_by(Device.mac_address)).scalars().all()
    content = build_csv_export(devices)
    filename = f"networkwatcher-devices-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
