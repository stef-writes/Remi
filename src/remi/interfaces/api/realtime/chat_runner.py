"""Chat agent runner — multi-turn conversation over WebSocket.

Thin transport adapter: delegates agent execution to ChatAgentService.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from remi.interfaces.api.realtime.jsonrpc import (
    Dispatcher,
    JsonRpcNotification,
    JsonRpcRequest,
)

if TYPE_CHECKING:
    from fastapi import WebSocket

    from remi.infrastructure.config.container import Container


async def send_notification(ws: WebSocket, method: str, params: dict[str, Any]) -> None:
    notif = JsonRpcNotification(method=method, params=params)
    await ws.send_text(notif.to_json())


def build_chat_dispatcher(ws: WebSocket, container: Container) -> Dispatcher:
    from remi.domain.modules.base import Message

    dp = Dispatcher()

    @dp.method("chat.create")
    async def chat_create(req: JsonRpcRequest) -> dict[str, Any]:
        agent = req.params.get("agent", "director")
        session = await container.chat_session_store.create(agent)
        return {"session_id": session.id, "agent": session.agent}

    @dp.method("chat.send")
    async def chat_send(req: JsonRpcRequest) -> dict[str, Any]:
        session_id = req.params.get("session_id")
        message_text = req.params.get("message", "")

        if not session_id:
            raise ValueError("session_id is required")

        session = await container.chat_session_store.get(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' not found")

        user_msg = Message(role="user", content=message_text)
        await container.chat_session_store.append_message(session_id, user_msg)

        session = await container.chat_session_store.get(session_id)
        assert session is not None

        async def on_event(event_type: str, data: dict[str, Any]) -> None:
            await send_notification(ws, f"chat.{event_type}", {
                "session_id": session_id, **data,
            })

        try:
            answer = await container.chat_agent.run_chat_agent(
                session.agent, session.thread, on_event
            )
        except Exception as exc:
            await send_notification(ws, "chat.error", {
                "session_id": session_id, "message": str(exc),
            })
            raise

        assistant_msg = Message(role="assistant", content=answer)
        await container.chat_session_store.append_message(session_id, assistant_msg)

        return {"status": "ok", "session_id": session_id}

    @dp.method("chat.history")
    async def chat_history(req: JsonRpcRequest) -> dict[str, Any]:
        session_id = req.params.get("session_id")
        if not session_id:
            raise ValueError("session_id is required")
        session = await container.chat_session_store.get(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' not found")
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
        sessions = await container.chat_session_store.list_sessions()
        return {
            "sessions": [
                {
                    "id": s.id, "agent": s.agent,
                    "message_count": len([m for m in s.thread if m.role in ("user", "assistant")]),
                    "created_at": s.created_at.isoformat(),
                    "updated_at": s.updated_at.isoformat(),
                }
                for s in sessions
            ],
        }

    return dp
