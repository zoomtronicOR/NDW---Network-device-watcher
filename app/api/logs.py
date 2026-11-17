from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Response

from app.services.log_reader import read_logs

router = APIRouter(prefix="/logs", tags=["logs"])

_FETCH_LIMIT = 5000


@router.get("")
def list_logs(
    source: str = "all",
    level: str | None = None,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    sort: str = "timestamp",
    order: str = "desc",
) -> dict:
    entries = read_logs(source=source, limit=_FETCH_LIMIT, since=since, until=until, search=search)
    if level:
        entries = [e for e in entries if e.level == level]
    entries = _sorted(entries, sort, order)

    total = len(entries)
    start = (page - 1) * page_size
    page_entries = entries[start : start + page_size]

    return {
        "total": total,
        "items": [
            {"timestamp": e.timestamp.isoformat(), "level": e.level, "source": e.source, "message": e.message}
            for e in page_entries
        ],
    }


_LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}


def _sorted(entries, sort: str, order: str):
    keys = {
        "timestamp": lambda e: e.timestamp,
        "level": lambda e: (_LEVEL_RANK.get(e.level, 1), e.timestamp),
        "source": lambda e: (e.source, e.timestamp),
        "message": lambda e: e.message.lower(),
    }
    return sorted(entries, key=keys.get(sort, keys["timestamp"]), reverse=order == "desc")


@router.get("/download")
def download_logs(
    source: str = "all", level: str | None = None, search: str | None = None, since: str | None = None
) -> Response:
    entries = read_logs(source=source, limit=_FETCH_LIMIT, since=since, search=search)
    if level:
        entries = [e for e in entries if e.level == level]

    lines = [
        f"{e.timestamp.astimezone().strftime('%Y-%m-%d %H:%M:%S')} [{e.level}] [{e.source}] {e.message}"
        for e in entries
    ]
    content = "\n".join(lines) + "\n"
    filename = f"networkwatcher-logs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
