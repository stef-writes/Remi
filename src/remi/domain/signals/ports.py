"""SignalStore port — storage for entailed signals."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remi.domain.signals.types import Signal


class SignalStore(abc.ABC):
    """Read/write access to entailed signals."""

    @abc.abstractmethod
    async def put_signal(self, signal: Signal) -> None: ...

    @abc.abstractmethod
    async def get_signal(self, signal_id: str) -> Signal | None: ...

    @abc.abstractmethod
    async def list_signals(
        self,
        *,
        manager_id: str | None = None,
        property_id: str | None = None,
        severity: str | None = None,
        signal_type: str | None = None,
    ) -> list[Signal]: ...

    @abc.abstractmethod
    async def retire_signal(self, signal_id: str) -> None: ...

    @abc.abstractmethod
    async def clear_all(self) -> None: ...
