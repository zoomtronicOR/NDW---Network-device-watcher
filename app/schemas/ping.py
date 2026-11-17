from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PingTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    address: str
    label: str | None
    enabled: bool
    created_at: datetime


class PingTargetCreate(BaseModel):
    address: str
    label: str | None = None


class PingTargetUpdate(BaseModel):
    label: str | None = None
    enabled: bool | None = None


class PingResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    reachable: bool
    packet_loss_pct: float
    rtt_min: float | None
    rtt_avg: float | None
    rtt_max: float | None
    rtt_mdev: float | None
    # Only set for bucketed (range) history: raw samples aggregated into this point.
    samples: int | None = None
    unreachable_samples: int | None = None


class PingSeriesOut(BaseModel):
    target: PingTargetOut
    latest: PingResultOut | None
    history: list[PingResultOut]


class ColorBand(BaseModel):
    max_ms: float | None  # None = "and above" (last band)
    color: str


class PingSettingsOut(BaseModel):
    interval_seconds: int
    color_bands: list[ColorBand]


class PingSettingsUpdate(BaseModel):
    interval_seconds: int | None = None
    color_bands: list[ColorBand] | None = None
