from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.services.ws_manager import manager

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            # Browser clients don't send anything; awaiting is just how we
            # detect the disconnect (WebSocketDisconnect) via the ASGI server.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


class BroadcastPayload(BaseModel):
    type: str
    new_devices: list[dict] = []
    returned: list[dict] = []
    went_offline: list[dict] = []
    burst_anomaly: bool = False
    anomaly: dict | None = None


@router.post("/internal/broadcast")
async def internal_broadcast(payload: BroadcastPayload, request: Request) -> dict:
    # Only the scanner process (same host) may trigger a broadcast -- this is
    # not a public API, so it's not exposed to the rest of the LAN.
    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "::1"):
        return {"ok": False, "error": "forbidden"}
    await manager.broadcast(payload.model_dump())
    return {"ok": True}
