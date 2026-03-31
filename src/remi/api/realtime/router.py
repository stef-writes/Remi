"""WebSocket routes — lifecycle event broadcast and JSON-RPC 2.0 chat."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from remi.api.realtime.chat_runner import build_chat_dispatcher
from remi.api.realtime.connection_manager import manager
from remi.api.realtime.jsonrpc import JsonRpcError, JsonRpcResponse

router = APIRouter(tags=["ws"])
logger = structlog.get_logger("remi.ws")


def _container(ws: WebSocket):
    """Extract the container from the app state (works for both HTTP and WS)."""
    return ws.app.state.container


@router.websocket("/ws/events")
async def events_ws(ws: WebSocket) -> None:
    client = ws.client.host if ws.client else "unknown"
    logger.info("ws_events_connect", client=client)
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        logger.info("ws_events_disconnect", client=client)
        manager.disconnect(ws)


@router.websocket("/ws/chat")
async def chat_ws(ws: WebSocket) -> None:
    client = ws.client.host if ws.client else "unknown"
    logger.info("ws_chat_connect", client=client)
    await ws.accept()
    container = _container(ws)
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
        logger.info("ws_chat_disconnect", client=client)
    except Exception:
        logger.exception("ws_chat_error", client=client)
        raise
