"""WebSocket routes — lifecycle event broadcast and JSON-RPC 2.0 chat.

The chat WebSocket runs agent work in background tasks so the receive loop
stays responsive to control messages like chat.stop while the agent runs.

Both endpoints run a server-side heartbeat loop that sends application-level
JSON ping messages (``{"type":"ping"}``).  The client is expected to reply
with ``{"type":"pong"}``.  If no pong arrives within PONG_TIMEOUT_S the
server considers the connection dead and closes it, which unblocks the
receive loop with a clean WebSocketDisconnect.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from remi.agent.observe.events import Event
from remi.application.realtime.chat_runner import build_chat_dispatcher
from remi.application.realtime.connection_manager import manager
from remi.application.realtime.jsonrpc import JsonRpcError, JsonRpcResponse

router = APIRouter(tags=["ws"])
logger = structlog.get_logger("remi.ws")

LONG_RUNNING_METHODS = frozenset({"chat.send"})
HEARTBEAT_INTERVAL_S = 25
PONG_TIMEOUT_S = 10

_PING_MSG = json.dumps({"type": "ping"})


class _Heartbeat:
    """Server-side heartbeat using app-level ping/pong JSON messages.

    Sends ``{"type":"ping"}`` every HEARTBEAT_INTERVAL_S seconds.
    Tracks the last pong timestamp.  If no pong arrives within
    PONG_TIMEOUT_S after a ping, closes the socket.
    """

    def __init__(self) -> None:
        self.last_pong: float = time.monotonic()

    def record_pong(self) -> None:
        self.last_pong = time.monotonic()

    async def run(self, ws: WebSocket, label: str) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_S)
                try:
                    await ws.send_text(_PING_MSG)
                except Exception:
                    logger.warning(Event.WS_PING_FAILED, endpoint=label, exc_info=True)
                    return

                await asyncio.sleep(PONG_TIMEOUT_S)
                if time.monotonic() - self.last_pong > HEARTBEAT_INTERVAL_S + PONG_TIMEOUT_S:
                    logger.warning("ws_pong_timeout", endpoint=label)
                    with contextlib.suppress(Exception):
                        await ws.close(code=4001, reason="pong timeout")
                    return
        except asyncio.CancelledError:
            pass


def _is_pong(raw: str) -> bool:
    """Check if a raw message is an app-level pong (fast path avoids full parse)."""
    return '"pong"' in raw and raw.strip().startswith("{")


@router.websocket("/ws/events")
async def events_ws(ws: WebSocket) -> None:
    client = ws.client.host if ws.client else "unknown"
    logger.info(Event.WS_EVENTS_CONNECT, client=client)
    await manager.connect(ws)
    hb = _Heartbeat()
    heartbeat_task = asyncio.create_task(hb.run(ws, "events"))
    try:
        while True:
            raw = await ws.receive_text()
            if _is_pong(raw):
                hb.record_pong()
    except WebSocketDisconnect:
        logger.info(Event.WS_EVENTS_DISCONNECT, client=client)
    finally:
        heartbeat_task.cancel()
        manager.disconnect(ws)


@router.websocket("/ws/chat")
async def chat_ws(ws: WebSocket) -> None:
    client = ws.client.host if ws.client else "unknown"
    logger.info(Event.WS_CONNECT, client=client)
    await ws.accept()
    c = ws.app.state.container
    handle = build_chat_dispatcher(
        ws,
        c.chat_session_store,
        c.chat_agent,
        property_store=c.property_store,
        sandbox=c.sandbox,
    )

    background_tasks: set[asyncio.Task[None]] = set()
    hb = _Heartbeat()
    heartbeat_task = asyncio.create_task(hb.run(ws, "chat"))

    async def _run_and_respond(request_id: str | int | None, raw_text: str) -> None:
        """Run a long-running RPC method in background, send result when done."""
        try:
            response = await handle.dispatch(raw_text)
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

            if _is_pong(raw):
                hb.record_pong()
                continue

            is_long_running = False
            try:
                data = json.loads(raw)
                method = data.get("method", "")
                is_long_running = method in LONG_RUNNING_METHODS
            except (json.JSONDecodeError, TypeError, AttributeError):
                logger.debug("ws_message_not_json", raw_length=len(raw))

            if is_long_running:
                request_id = data.get("id")
                task = asyncio.create_task(_run_and_respond(request_id, raw))
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)
            else:
                response = await handle.dispatch(raw)
                await ws.send_text(
                    response.to_json()
                    if isinstance(response, (JsonRpcResponse, JsonRpcError))
                    else response.model_dump_json()
                )
    except WebSocketDisconnect:
        logger.info(Event.WS_DISCONNECT, client=client)
    except Exception:
        logger.exception(Event.WS_ERROR, client=client)
        raise
    finally:
        heartbeat_task.cancel()
        for task in background_tasks:
            task.cancel()
        await handle.cleanup()
