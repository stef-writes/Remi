"""Chat agent runner — multi-turn conversation over WebSocket.

Thin transport adapter: delegates agent execution to ChatAgentService.
Tracks running tasks per session for server-side cancellation.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import WebSocket

from remi.agent.runner import ChatAgentService
from remi.api.realtime.jsonrpc import (
    Dispatcher,
    JsonRpcNotification,
    JsonRpcRequest,
)
from remi.models.chat import ChatSessionStore
from remi.observability.events import Event
from remi.shared.errors import SessionNotFoundError, ValidationError

logger = structlog.get_logger("remi.chat_runner")


async def _resolve_manager_scope(
    property_store: Any,
    manager_id: str | None,
) -> dict[str, Any]:
    """Build extras dict with manager scope info when a manager is selected."""
    if not manager_id or property_store is None:
        return {}
    try:
        mgr = await property_store.get_manager(manager_id)
        if mgr is None:
            return {}
        portfolios = await property_store.list_portfolios(manager_id=manager_id)

        # Gather property lists across all portfolios concurrently
        portfolio_props = await asyncio.gather(*[
            property_store.list_properties(portfolio_id=p.id)
            for p in portfolios
        ])
        all_props = [prop for props in portfolio_props for prop in props]

        # Gather unit counts across all properties concurrently
        unit_lists = await asyncio.gather(*[
            property_store.list_units(property_id=prop.id)
            for prop in all_props
        ])

        property_names = [prop.name for prop in all_props]
        total_units = sum(len(units) for units in unit_lists)

        return {
            "manager_id": manager_id,
            "manager_name": mgr.name,
            "manager_property_count": len(property_names),
            "manager_property_names": property_names,
            "manager_unit_count": total_units,
        }
    except Exception:
        logger.debug("manager_scope_resolve_failed", manager_id=manager_id, exc_info=True)
        return {"manager_id": manager_id}


async def send_notification(ws: WebSocket, method: str, params: dict[str, Any]) -> None:
    notif = JsonRpcNotification(method=method, params=params)
    await ws.send_text(notif.to_json())


def build_chat_dispatcher(
    ws: WebSocket,
    chat_session_store: ChatSessionStore,
    chat_agent: ChatAgentService,
    *,
    property_store: Any = None,
) -> Dispatcher:
    from remi.models.chat import Message

    dp = Dispatcher()
    running_tasks: dict[str, asyncio.Task[str]] = {}
    session_locks: dict[str, asyncio.Lock] = {}

    def _get_session_lock(session_id: str) -> asyncio.Lock:
        if session_id not in session_locks:
            session_locks[session_id] = asyncio.Lock()
        return session_locks[session_id]

    @dp.method("chat.create")
    async def chat_create(req: JsonRpcRequest) -> dict[str, Any]:
        agent = req.params.get("agent", "director")
        provider = req.params.get("provider")
        model = req.params.get("model")
        session = await chat_session_store.create(
            agent,
            provider=provider,
            model=model,
        )
        return {
            "session_id": session.id,
            "agent": session.agent,
            "provider": session.provider,
            "model": session.model,
        }

    @dp.method("chat.send")
    async def chat_send(req: JsonRpcRequest) -> dict[str, Any]:
        session_id = req.params.get("session_id")
        message_text = req.params.get("message", "")
        mode = req.params.get("mode", "agent")
        if mode not in ("ask", "agent"):
            mode = "agent"

        req_provider = req.params.get("provider")
        req_model = req.params.get("model")
        manager_id = req.params.get("manager_id")

        if not session_id:
            raise ValueError("session_id is required")

        lock = _get_session_lock(session_id)
        async with lock:
            log = logger.bind(session_id=session_id, mode=mode, manager_id=manager_id)
            log.info(
                "chat_send",
                message_length=len(message_text),
                provider=req_provider,
                model=req_model,
            )

            session = await chat_session_store.get(session_id)
            if session is None:
                raise ValueError(f"Session '{session_id}' not found")

            provider = req_provider or session.provider
            model = req_model or session.model

            manager_scope = await _resolve_manager_scope(property_store, manager_id)

            user_msg = Message(role="user", content=message_text)
            await chat_session_store.append_message(session_id, user_msg)

            session = await chat_session_store.get(session_id)
            assert session is not None

            async def on_event(event_type: str, data: dict[str, Any]) -> None:
                try:
                    await asyncio.wait_for(
                        send_notification(
                            ws,
                            f"chat.{event_type}",
                            {"session_id": session_id, **data},
                        ),
                        timeout=10.0,
                    )
                except (asyncio.TimeoutError, Exception):
                    log.debug("notification_send_failed", event_type=event_type)

            async def _run_agent() -> str:
                return await chat_agent.run_chat_agent(
                    session.agent,
                    session.thread,
                    on_event,
                    mode=mode,
                    sandbox_session_id=f"chat-{session_id}",
                    provider=provider,
                    model=model,
                    extra=manager_scope,
                )

            task = asyncio.current_task()
            assert task is not None
            running_tasks[session_id] = task

            try:
                answer = await _run_agent()
            except asyncio.CancelledError:
                log.info("chat_send_cancelled", session_id=session_id)
                try:
                    await send_notification(
                        ws,
                        "chat.done",
                        {
                            "session_id": session_id,
                            "response": "",
                            "cancelled": True,
                        },
                    )
                except Exception:
                    pass
                raise
            except Exception as exc:
                log.error("chat_send_error", error=str(exc), error_type=type(exc).__name__)
                error_msg = Message(
                    role="assistant",
                    content=f"[Error: {type(exc).__name__} — {exc}]",
                )
                await chat_session_store.append_message(session_id, error_msg)
                await send_notification(
                    ws,
                    "chat.error",
                    {
                        "session_id": session_id,
                        "message": str(exc),
                    },
                )
                raise
            finally:
                running_tasks.pop(session_id, None)

            assistant_msg = Message(role="assistant", content=answer)
            await chat_session_store.append_message(session_id, assistant_msg)

            return {"status": "ok", "session_id": session_id}

    @dp.method("chat.stop")
    async def chat_stop(req: JsonRpcRequest) -> dict[str, Any]:
        session_id = req.params.get("session_id")
        if not session_id:
            raise ValueError("session_id is required")
        task = running_tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()
            logger.info("chat_stop", session_id=session_id)
            return {"status": "stopped", "session_id": session_id}
        return {"status": "not_running", "session_id": session_id}

    @dp.method("chat.history")
    async def chat_history(req: JsonRpcRequest) -> dict[str, Any]:
        session_id = req.params.get("session_id")
        if not session_id:
            raise ValidationError("session_id is required", field="session_id")
        session = await chat_session_store.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return {
            "session_id": session.id,
            "agent": session.agent,
            "messages": [
                {"role": m.role, "content": m.content, "name": m.name}
                for m in session.thread
                if m.role in ("user", "assistant")
            ],
        }

    @dp.method("chat.list")
    async def chat_list(req: JsonRpcRequest) -> dict[str, Any]:
        sessions = await chat_session_store.list_sessions()
        return {
            "sessions": [
                {
                    "id": s.id,
                    "agent": s.agent,
                    "message_count": len([m for m in s.thread if m.role in ("user", "assistant")]),
                    "created_at": s.created_at.isoformat(),
                    "updated_at": s.updated_at.isoformat(),
                }
                for s in sessions
            ],
        }

    return dp
