"""In-memory implementation of ChatSessionStore."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog

from remi.models.chat import ChatSession, ChatSessionStore, Message

_log = structlog.get_logger(__name__)

_DEFAULT_MAX_SESSIONS = 200
_DEFAULT_TTL = timedelta(hours=24)


class InMemoryChatSessionStore(ChatSessionStore):
    def __init__(
        self,
        max_sessions: int = _DEFAULT_MAX_SESSIONS,
        ttl: timedelta = _DEFAULT_TTL,
    ) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._max_sessions = max_sessions
        self._ttl = ttl

    def _evict_expired(self) -> None:
        """Remove sessions older than TTL."""
        cutoff = datetime.now(UTC) - self._ttl
        expired = [
            sid for sid, s in self._sessions.items()
            if s.updated_at < cutoff
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            _log.debug("sessions_evicted", count=len(expired), reason="ttl")

    def _evict_oldest_if_full(self) -> None:
        """If at capacity, drop the least-recently-updated sessions."""
        if len(self._sessions) < self._max_sessions:
            return
        by_age = sorted(self._sessions.items(), key=lambda kv: kv[1].updated_at)
        to_remove = len(self._sessions) - self._max_sessions + 1
        for sid, _ in by_age[:to_remove]:
            del self._sessions[sid]
        _log.debug("sessions_evicted", count=to_remove, reason="capacity")

    async def create(
        self,
        agent: str,
        session_id: str | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> ChatSession:
        self._evict_expired()
        self._evict_oldest_if_full()

        sid = session_id or f"chat-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        session = ChatSession(
            id=sid,
            agent=agent,
            provider=provider,
            model=model,
            created_at=now,
            updated_at=now,
        )
        self._sessions[sid] = session
        return session

    async def get(self, session_id: str) -> ChatSession | None:
        session = self._sessions.get(session_id)
        if session is not None:
            cutoff = datetime.now(UTC) - self._ttl
            if session.updated_at < cutoff:
                del self._sessions[session_id]
                return None
        return session

    async def append_message(self, session_id: str, message: Message) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' not found")
        updated_thread = list(session.thread) + [message]
        self._sessions[session_id] = session.model_copy(
            update={"thread": updated_thread, "updated_at": datetime.now(UTC)}
        )

    async def list_sessions(self) -> list[ChatSession]:
        self._evict_expired()
        return sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)

    async def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None
