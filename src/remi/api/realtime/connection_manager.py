"""WebSocket connection manager for broadcasting events to clients."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = structlog.get_logger("remi.ws.broadcast")


class ConnectionManager:
    """Tracks active WebSocket connections and fans out events."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections = [c for c in self._connections if c is not ws]

    async def broadcast(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, default=str)
        stale: list[WebSocket] = []
        for conn in self._connections:
            try:
                await conn.send_text(payload)
            except Exception:
                logger.warning(
                    "broadcast_send_failed",
                    client=getattr(conn.client, "host", "unknown"),
                )
                stale.append(conn)
        for s in stale:
            self.disconnect(s)


manager = ConnectionManager()
