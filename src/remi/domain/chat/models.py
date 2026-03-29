"""Chat session and event models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from remi.domain.modules.base import Message


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ChatSession(BaseModel):
    """A persistent multi-turn conversation with a REMI agent."""

    id: str
    agent: str = "director"
    thread: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ChatEvent(BaseModel):
    """A streaming event emitted during agent execution."""

    event_type: str  # delta, tool_call, tool_result, done, error
    session_id: str
    data: dict[str, Any] = Field(default_factory=dict)
