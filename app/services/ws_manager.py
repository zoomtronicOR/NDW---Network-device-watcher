from __future__ import annotations

import json
import logging

from fastapi import WebSocket

logger = logging.getLogger("networkwatcher.ws")


class ConnectionManager:
    """Tracks connected browser WebSocket clients for real-time push
    (§41). The scanner runs as a separate OS process, so it
    can't hold these connections itself -- it relays through the internal
    broadcast endpoint instead (see app/api/ws.py).
    """

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        payload = json.dumps(message)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
