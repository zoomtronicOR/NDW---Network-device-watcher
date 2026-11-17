from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PingResult(Base):
    __tablename__ = "ping_results"
    __table_args__ = (Index("ix_ping_results_target_ts", "target_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("ping_targets.id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    reachable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    packet_loss_pct: Mapped[float] = mapped_column(Float, nullable=False)
    rtt_min: Mapped[float | None] = mapped_column(Float)
    rtt_avg: Mapped[float | None] = mapped_column(Float)
    rtt_max: Mapped[float | None] = mapped_column(Float)
    rtt_mdev: Mapped[float | None] = mapped_column(Float)

    target: Mapped["PingTarget"] = relationship(back_populates="results")
