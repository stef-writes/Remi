"""WebSocket routes — lifecycle event broadcast and JSON-RPC 2.0 chat.

The chat WebSocket runs agent work in background tasks so the receive loop
stays responsive to control messages like chat.stop while the agent runs.
"""

from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from remi.api.realtime.chat_runner import build_chat_dispatcher
from remi.api.realtime.connection_manager import manager
from remi.api.realtime.jsonrpc import JsonRpcError, JsonRpcRequest, JsonRpcResponse
from remi.observability.events import Event

router = APIRouter(tags=["ws"])
logger = structlog.get_logger("remi.ws")

LONG_RUNNING_METHODS = frozenset({"chat.send"})


@router.websocket("/ws/events")
async def events_ws(ws: WebSocket) -> None:
    client = ws.client.host if ws.client else "unknown"
    logger.info(Event.WS_EVENTS_CONNECT, client=client)
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        logger.info(Event.WS_EVENTS_DISCONNECT, client=client)
        manager.disconnect(ws)


@router.websocket("/ws/chat")
async def chat_ws(ws: WebSocket) -> None:
    client = ws.client.host if ws.client else "unknown"
    logger.info(Event.WS_CONNECT, client=client)
    await ws.accept()
    c = ws.app.state.container
    dispatcher = build_chat_dispatcher(
        ws, c.chat_session_store, c.chat_agent, property_store=c.property_store,
    )

    background_tasks: set[asyncio.Task[None]] = set()

    async def _run_and_respond(request_id: str | int | None, raw_text: str) -> None:
        """Run a long-running RPC method in background, send result when done."""
        try:
            response = await dispatcher.dispatch(raw_text)
            await ws.send_text(
                response.to_json()
                if isinstance(response, (JsonRpcResponse, JsonRpcError))
                else response.model_dump_json()
            )
        except asyncio.CancelledError:
            logger.debug(Event.WS_RPC_CANCELLED, request_id=request_id)
        except Exception:
            logger.warning(Event.WS_RPC_SEND_FAILED, request_id=request_id, exc_info=True)

    try:
        while True:
            raw = await ws.receive_text()

            is_long_running = False
            try:
                data = json.loads(raw)
                method = data.get("method", "")
                is_long_running = method in LONG_RUNNING_METHODS
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass

            if is_long_running:
                request_id = data.get("id")
                task = asyncio.create_task(_run_and_respond(request_id, raw))
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)
            else:
                response = await dispatcher.dispatch(raw)
                await ws.send_text(
                    response.to_json()
                    if isinstance(response, (JsonRpcResponse, JsonRpcError))
                    else response.model_dump_json()
                )
    except WebSocketDisconnect:
        logger.info(Event.WS_DISCONNECT, client=client)
        for task in background_tasks:
            task.cancel()
    except Exception:
        logger.exception(Event.WS_ERROR, client=client)
        for task in background_tasks:
            task.cancel()
        raise
