from __future__ import annotations

from pydantic import BaseModel

from app.schemas.device import DeviceEventOut


class EventListResponse(BaseModel):
    items: list[DeviceEventOut]
    total: int
