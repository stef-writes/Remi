"""In-memory implementation of SignalStore."""

from __future__ import annotations

from remi.domain.signals.ports import SignalStore
from remi.domain.signals.types import Severity, Signal

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


class InMemorySignalStore(SignalStore):

    def __init__(self) -> None:
        self._signals: dict[str, Signal] = {}

    async def put_signal(self, signal: Signal) -> None:
        self._signals[signal.signal_id] = signal

    async def get_signal(self, signal_id: str) -> Signal | None:
        return self._signals.get(signal_id)

    async def list_signals(
        self,
        *,
        manager_id: str | None = None,
        property_id: str | None = None,
        severity: str | None = None,
        signal_type: str | None = None,
    ) -> list[Signal]:
        results = list(self._signals.values())

        if manager_id is not None:
            results = [
                s for s in results
                if s.entity_id == manager_id
                or s.evidence.get("manager_id") == manager_id
            ]
        if property_id is not None:
            results = [
                s for s in results
                if s.entity_id == property_id
                or s.evidence.get("property_id") == property_id
            ]
        if severity is not None:
            results = [s for s in results if s.severity.value == severity]
        if signal_type is not None:
            results = [s for s in results if s.signal_type == signal_type]

        results.sort(key=lambda s: (_SEVERITY_ORDER.get(s.severity, 9), s.signal_type))
        return results

    async def retire_signal(self, signal_id: str) -> None:
        self._signals.pop(signal_id, None)

    async def clear_all(self) -> None:
        self._signals.clear()
