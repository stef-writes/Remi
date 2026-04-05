"""REST endpoints for agent discovery, model listing, and streaming chat."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
import yaml
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from remi.agent.observe import Event
from remi.agent.types import Message
from remi.shell.api.dependencies import Ctr
from remi.types.paths import AGENTS_DIR

logger = structlog.get_logger("remi.api.agents")

router = APIRouter(prefix="/agents", tags=["ai"])


@router.get("/models")
async def list_models(c: Ctr) -> dict[str, Any]:
    """Return available LLM providers/models and current defaults."""
    available = c.provider_factory.available()

    provider_models: dict[str, list[str]] = {
        "openai": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "o3",
            "o3-mini",
            "o4-mini",
        ],
        "anthropic": [
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-sonnet-4-5-20250929",
            "claude-haiku-4-5-20251001",
        ],
        "gemini": [
            "gemini-2.5-pro-preview-05-06",
            "gemini-2.5-flash-preview-04-17",
            "gemini-2.0-flash",
        ],
    }

    return {
        "default_provider": c.settings.llm.default_provider,
        "default_model": c.settings.llm.default_model,
        "providers": [
            {
                "name": name,
                "available": name in available,
                "models": provider_models.get(name, []),
            }
            for name in ["openai", "anthropic", "gemini"]
        ],
    }


@router.get("")
async def list_agents() -> dict[str, Any]:
    """List user-facing agents available for chat.

    Reads metadata from each agent's app.yaml and filters to those
    marked with ``audience: director`` and ``chat: true``.
    """
    agents: list[dict[str, Any]] = []
    if not AGENTS_DIR.exists():
        return {"agents": agents}

    for app_dir in sorted(AGENTS_DIR.iterdir()):
        app_yaml = app_dir / "app.yaml"
        if not app_yaml.is_file():
            continue
        try:
            with open(app_yaml) as f:
                raw = yaml.safe_load(f)
            meta = raw.get("metadata", {})
            if meta.get("audience") == "system" or meta.get("chat") is False:
                continue
            agents.append(
                {
                    "name": meta.get("name", app_dir.name),
                    "description": meta.get("description", ""),
                    "version": meta.get("version", ""),
                    "primary": meta.get("primary", False),
                    "tags": meta.get("tags", []),
                }
            )
        except Exception:
            logger.warning(Event.AGENT_CONFIG_INVALID, agent_dir=app_dir.name, exc_info=True)
            continue

    agents.sort(key=lambda a: (not a["primary"], a["name"]))
    return {"agents": agents}


# ---------------------------------------------------------------------------
# Streaming agent ask — pipes on_event into newline-delimited JSON
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    question: str
    session_id: str | None = None
    mode: str = "agent"


@router.post("/{agent_name}/ask")
async def ask_agent(
    agent_name: str,
    body: AskRequest,
    c: Ctr,
) -> StreamingResponse:
    """Stream an agent response as newline-delimited JSON events.

    Each line is a JSON object with ``event`` and ``data`` keys,
    matching the same event types the runtime already emits:
    ``delta``, ``tool_call``, ``tool_result``, ``phase``, ``done``.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _on_event(event_type: str, data: dict[str, Any]) -> None:
        line = json.dumps({"event": event_type, "data": data}, default=str)
        await queue.put(line)

    async def _run() -> None:
        try:
            if body.session_id:
                session = await c.chat_session_store.get(body.session_id)
                if session is None:
                    await queue.put(
                        json.dumps({"event": "error", "data": {"message": "session not found"}})
                    )
                    return

                user_msg = Message(role="user", content=body.question)
                await c.chat_session_store.append_message(body.session_id, user_msg)
                refreshed = await c.chat_session_store.get(body.session_id)
                thread = list(refreshed.thread) if refreshed else [user_msg]

                answer = await c.chat_agent.run_chat_agent(
                    session.agent,
                    thread,
                    on_event=_on_event,
                    sandbox_session_id=session.sandbox_session_id,
                    mode=body.mode,  # type: ignore[arg-type]
                )
                assistant_msg = Message(role="assistant", content=answer)
                await c.chat_session_store.append_message(body.session_id, assistant_msg)
            else:
                await c.chat_agent.ask(
                    agent_name,
                    body.question,
                    mode=body.mode,  # type: ignore[arg-type]
                    on_event=_on_event,
                )
        except Exception:
            logger.warning("ask_stream_failed", agent=agent_name, exc_info=True)
            await queue.put(
                json.dumps({"event": "error", "data": {"message": "agent execution failed"}})
            )
        finally:
            await queue.put(None)

    async def _stream() -> AsyncIterator[str]:
        task = asyncio.create_task(_run())
        try:
            while True:
                line = await queue.get()
                if line is None:
                    break
                yield line + "\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Session CRUD — REST surface over ChatSessionStore
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    agent: str = "director"
    provider: str | None = None
    model: str | None = None


@router.post("/sessions")
async def create_session(
    body: CreateSessionRequest,
    c: Ctr,
) -> dict[str, Any]:
    session = await c.chat_session_store.create(
        body.agent,
        provider=body.provider,
        model=body.model,
    )
    return _session_dict(session)


@router.get("/sessions")
async def list_sessions(c: Ctr) -> dict[str, Any]:
    all_sessions = await c.chat_session_store.list_sessions()
    return {
        "count": len(all_sessions),
        "sessions": [_session_summary(s) for s in all_sessions],
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    c: Ctr,
) -> dict[str, Any]:
    from remi.types.errors import NotFoundError

    session = await c.chat_session_store.get(session_id)
    if session is None:
        raise NotFoundError("Session", session_id)
    return _session_dict(session)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    c: Ctr,
) -> dict[str, Any]:
    deleted = await c.chat_session_store.delete(session_id)
    return {"deleted": deleted, "session_id": session_id}


def _session_dict(s: Any) -> dict[str, Any]:
    return {
        "session_id": s.id,
        "agent": s.agent,
        "provider": s.provider,
        "model": s.model,
        "sandbox_session_id": s.sandbox_session_id,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
        "message_count": len(s.thread),
        "messages": [{"role": m.role, "content": m.content} for m in s.thread],
    }


def _session_summary(s: Any) -> dict[str, Any]:
    return {
        "session_id": s.id,
        "agent": s.agent,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
        "message_count": len(s.thread),
    }
