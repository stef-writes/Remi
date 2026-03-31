"""WebSocket routes — lifecycle event broadcast and JSON-RPC 2.0 chat."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from remi.interfaces.api.dependencies import get_container
from remi.interfaces.api.realtime.chat_runner import build_chat_dispatcher
from remi.interfaces.api.realtime.connection_manager import manager
from remi.interfaces.api.realtime.jsonrpc import JsonRpcError, JsonRpcResponse

if TYPE_CHECKING:
    from remi.infrastructure.config.container import Container

router = APIRouter(tags=["ws"])


@router.websocket("/ws/events")
async def events_ws(
    ws: WebSocket,
    container: Container = Depends(get_container),
) -> None:
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


@router.websocket("/ws/chat")
async def chat_ws(
    ws: WebSocket,
    container: Container = Depends(get_container),
) -> None:
    await ws.accept()
    dispatcher = build_chat_dispatcher(ws, container)

    try:
        while True:
            raw = await ws.receive_text()
            response = await dispatcher.dispatch(raw)
            await ws.send_text(
                response.to_json()
                if isinstance(response, (JsonRpcResponse, JsonRpcError))
                else response.model_dump_json()
            )
    except WebSocketDisconnect:
        pass
