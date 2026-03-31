"""Chat models — Message, ToolCallRequest, ChatSession, and persistence ports."""

from __future__ import annotations

import abc
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel, frozen=True):
    """A single tool invocation requested by the model.

    Pydantic model so it composes cleanly inside Message (also Pydantic).
    """

    id: str
    name: str
    arguments: dict[str, Any]


class Message(BaseModel, frozen=True):
    """A single entry in a conversation thread passed between agent nodes."""

    role: str
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCallRequest] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ChatSession(BaseModel):
    """A persistent multi-turn conversation with a REMI agent."""

    id: str
    agent: str = "director"
    provider: str | None = None
    model: str | None = None
    thread: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class AgentEvent(BaseModel, frozen=True):
    """Typed payload for agent runtime events (tool calls, deltas, etc.)."""

    event_type: str
    content: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_result: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatEvent(BaseModel):
    """A streaming event emitted during agent execution."""

    event_type: str  # delta, tool_call, tool_result, done, error
    session_id: str
    data: dict[str, Any] = Field(default_factory=dict)


class ChatSessionStore(abc.ABC):
    @abc.abstractmethod
    async def create(
        self,
        agent: str,
        session_id: str | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> ChatSession: ...

    @abc.abstractmethod
    async def get(self, session_id: str) -> ChatSession | None: ...

    @abc.abstractmethod
    async def append_message(self, session_id: str, message: Message) -> None: ...

    @abc.abstractmethod
    async def list_sessions(self) -> list[ChatSession]: ...

    @abc.abstractmethod
    async def delete(self, session_id: str) -> bool: ...
