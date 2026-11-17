from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import charts, devices, events, export, logs, notifications, ping, settings, stats, telemetry, timemachine, ws
from app.version import __version__

app = FastAPI(title="Network Device Watcher", version=__version__)

app.include_router(devices.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(charts.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(ws.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(timemachine.router, prefix="/api")
app.include_router(ping.router, prefix="/api")
app.include_router(telemetry.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")


@app.middleware("http")
async def revalidate_static(request, call_next):
    # StaticFiles sends ETag/Last-Modified but no Cache-Control, so browsers
    # heuristically cached JS/CSS and kept serving the old UI after a deploy.
    # "no-cache" = always revalidate (cheap 304 when unchanged).
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/version")
def version() -> dict[str, str]:
    return {"version": __version__}


_uploads_dir = Path(__file__).resolve().parent.parent / "uploads" / "backgrounds"
_uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/backgrounds", StaticFiles(directory=_uploads_dir), name="uploads")

_static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
