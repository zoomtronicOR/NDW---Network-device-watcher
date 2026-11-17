from __future__ import annotations

from fastapi import APIRouter

from app.services.telemetry import collect_telemetry

router = APIRouter(tags=["telemetry"])


@router.get("/telemetry")
def get_telemetry() -> dict:
    return collect_telemetry()
