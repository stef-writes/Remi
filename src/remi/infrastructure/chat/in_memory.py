"""In-memory implementation of ChatSessionStore."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from remi.domain.chat.models import ChatSession
from remi.domain.chat.ports import ChatSessionStore
from remi.domain.modules.base import Message


class InMemoryChatSessionStore(ChatSessionStore):

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}

    async def create(self, agent: str, session_id: str | None = None) -> ChatSession:
        sid = session_id or f"chat-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        session = ChatSession(id=sid, agent=agent, created_at=now, updated_at=now)
        self._sessions[sid] = session
        return session

    async def get(self, session_id: str) -> ChatSession | None:
        return self._sessions.get(session_id)

    async def append_message(self, session_id: str, message: Message) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' not found")
        updated_thread = list(session.thread) + [message]
        self._sessions[session_id] = session.model_copy(
            update={"thread": updated_thread, "updated_at": datetime.now(UTC)}
        )

    async def list_sessions(self) -> list[ChatSession]:
        return sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)

    async def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None
