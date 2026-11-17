from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ping_result import PingResult
from app.models.ping_target import PingTarget
from app.schemas.ping import PingResultOut, PingSeriesOut, PingTargetCreate, PingTargetOut, PingTargetUpdate

router = APIRouter(prefix="/ping", tags=["ping"])


@router.get("/targets", response_model=list[PingTargetOut])
def list_targets(db: Session = Depends(get_db)) -> list[PingTarget]:
    return db.execute(select(PingTarget).order_by(PingTarget.created_at)).scalars().all()


@router.post("/targets", response_model=PingTargetOut)
def create_target(payload: PingTargetCreate, db: Session = Depends(get_db)) -> PingTarget:
    address = payload.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Adresa ne sme biti prazna")
    target = PingTarget(address=address, label=(payload.label or "").strip() or None)
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


@router.patch("/targets/{target_id}", response_model=PingTargetOut)
def update_target(target_id: int, payload: PingTargetUpdate, db: Session = Depends(get_db)) -> PingTarget:
    target = db.get(PingTarget, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Destinacija nije pronađena")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(target, key, value)
    db.commit()
    db.refresh(target)
    return target


@router.delete("/targets/{target_id}", status_code=204)
def delete_target(target_id: int, db: Session = Depends(get_db)) -> None:
    target = db.get(PingTarget, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Destinacija nije pronađena")
    db.delete(target)
    db.commit()


_MAX_RANGE_HOURS = 24 * 90


@router.get("/series", response_model=list[PingSeriesOut])
def get_series(
    hours: float | None = None,
    buckets: int = 240,
    limit: int = 60,
    db: Session = Depends(get_db),
) -> list[PingSeriesOut]:
    """Per-target RTT history.

    hours=None keeps the old behaviour (last `limit` raw samples). With
    `hours`, the window is aggregated server-side into ~`buckets` time
    buckets: at a few-second ping interval, 10 days is ~290k raw rows per
    target -- far too many to ship to the browser or draw.
    """
    targets = db.execute(select(PingTarget).order_by(PingTarget.created_at)).scalars().all()

    latest_by_target: dict[int, PingResultOut] = {}
    for target in targets:
        row = db.execute(
            select(PingResult)
            .where(PingResult.target_id == target.id)
            .order_by(PingResult.timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            latest_by_target[target.id] = PingResultOut.model_validate(row)

    history_by_target: dict[int, list[PingResultOut]] = {t.id: [] for t in targets}
    if hours is None:
        for target in targets:
            rows = (
                db.execute(
                    select(PingResult)
                    .where(PingResult.target_id == target.id)
                    .order_by(PingResult.timestamp.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            history_by_target[target.id] = [PingResultOut.model_validate(r) for r in reversed(rows)]
    else:
        hours = max(0.1, min(float(hours), _MAX_RANGE_HOURS))
        buckets = max(20, min(buckets, 1000))
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)
        bucket_seconds = max(1, int(hours * 3600 / buckets))

        bucket = func.to_timestamp(
            func.floor(func.extract("epoch", PingResult.timestamp) / bucket_seconds) * bucket_seconds
        ).label("bucket")
        reachable_avg = func.avg(PingResult.rtt_avg).filter(PingResult.reachable.is_(True))
        rows = db.execute(
            select(
                PingResult.target_id,
                bucket,
                func.bool_or(PingResult.reachable),
                func.avg(PingResult.packet_loss_pct),
                func.min(PingResult.rtt_min),
                reachable_avg,
                func.max(PingResult.rtt_max),
                func.count(),
                func.count().filter(PingResult.reachable.is_(False)),
            )
            .where(PingResult.timestamp >= start)
            .group_by(PingResult.target_id, bucket)
            .order_by(PingResult.target_id, bucket)
        ).all()
        for target_id, ts, any_ok, loss, rmin, ravg, rmax, n, n_down in rows:
            if target_id not in history_by_target:
                continue
            history_by_target[target_id].append(
                PingResultOut(
                    timestamp=ts,
                    reachable=bool(any_ok) and ravg is not None,
                    packet_loss_pct=float(loss or 0),
                    rtt_min=rmin,
                    rtt_avg=float(ravg) if ravg is not None else None,
                    rtt_max=rmax,
                    rtt_mdev=None,
                    samples=n,
                    unreachable_samples=n_down,
                )
            )

    return [
        PingSeriesOut(
            target=PingTargetOut.model_validate(t),
            latest=latest_by_target.get(t.id),
            history=history_by_target[t.id],
        )
        for t in targets
    ]
