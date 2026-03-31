"""Abstract store interfaces for signals, feedback, and hypotheses."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remi.models.signals.enums import HypothesisStatus
    from remi.models.signals.feedback import SignalFeedback, SignalFeedbackSummary
    from remi.models.signals.hypothesis import Hypothesis
    from remi.models.signals.signal import Signal


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


class FeedbackStore(abc.ABC):
    """Read/write access to signal feedback data."""

    @abc.abstractmethod
    async def record_feedback(self, feedback: SignalFeedback) -> None: ...

    @abc.abstractmethod
    async def get_feedback(self, feedback_id: str) -> SignalFeedback | None: ...

    @abc.abstractmethod
    async def list_feedback(
        self,
        *,
        signal_id: str | None = None,
        signal_type: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[SignalFeedback]: ...

    @abc.abstractmethod
    async def summarize(self, signal_type: str) -> SignalFeedbackSummary: ...


class HypothesisStore(abc.ABC):
    """Storage for candidate TBox entries awaiting review."""

    @abc.abstractmethod
    async def put(self, hypothesis: Hypothesis) -> None: ...

    @abc.abstractmethod
    async def get(self, hypothesis_id: str) -> Hypothesis | None: ...

    @abc.abstractmethod
    async def list_hypotheses(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
        min_confidence: float | None = None,
        limit: int = 50,
    ) -> list[Hypothesis]: ...

    @abc.abstractmethod
    async def update_status(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        *,
        reviewed_by: str = "",
        review_notes: str = "",
    ) -> Hypothesis | None: ...
