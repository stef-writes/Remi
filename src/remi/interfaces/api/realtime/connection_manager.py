"""WebSocket connection manager for lifecycle event broadcast."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from remi.runtime.events.lifecycle import LifecycleEvent, ModuleEvent

if TYPE_CHECKING:
    from fastapi import WebSocket

    from remi.infrastructure.config.container import Container


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
                stale.append(conn)
        for s in stale:
            self.disconnect(s)


manager = ConnectionManager()


def event_to_dict(event: LifecycleEvent) -> dict[str, Any]:
    data: dict[str, Any] = {
        "event": event.event_type,
        "app_id": event.app_id,
        "run_id": event.run_id,
        "timestamp": event.timestamp.isoformat(),
    }
    if isinstance(event, ModuleEvent):
        data["module_id"] = event.module_id
        if event.error:
            data["error"] = event.error
        data.update(event.metadata)
    else:
        data.update(event.metadata)
    return data


def wire_event_bus(container: Container) -> None:
    """Subscribe the WS manager to all lifecycle events."""

    async def _handler(event: LifecycleEvent) -> None:
        await manager.broadcast(event_to_dict(event))

    container.event_bus.subscribe("*", _handler)
