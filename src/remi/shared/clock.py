"""Abstraction over time for testability."""

from __future__ import annotations

import abc
from datetime import UTC, datetime


class Clock(abc.ABC):
    @abc.abstractmethod
    def now(self) -> datetime: ...


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock(Clock):
    """Deterministic clock for testing."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed

    def advance(self, **kwargs: float) -> None:
        from datetime import timedelta

        self._fixed += timedelta(**kwargs)
