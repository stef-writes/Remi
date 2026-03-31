"""Chat session store port."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remi.domain.chat.models import ChatSession
    from remi.domain.modules.base import Message


class ChatSessionStore(abc.ABC):

    @abc.abstractmethod
    async def create(self, agent: str, session_id: str | None = None) -> ChatSession: ...

    @abc.abstractmethod
    async def get(self, session_id: str) -> ChatSession | None: ...

    @abc.abstractmethod
    async def append_message(self, session_id: str, message: Message) -> None: ...

    @abc.abstractmethod
    async def list_sessions(self) -> list[ChatSession]: ...

    @abc.abstractmethod
    async def delete(self, session_id: str) -> bool: ...
