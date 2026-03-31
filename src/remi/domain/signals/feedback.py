"""FeedbackStore port — tracks how users respond to signals.

This is the learning loop's data layer. Every time a signal is acknowledged,
dismissed, or acted upon, that outcome is recorded. Over time this data
enables:

- Severity re-weighting (signals that are always dismissed lose priority)
- Threshold tuning (thresholds that produce too many false positives adjust)
- Producer ranking (statistical detections that get acted on may graduate
  to hand-authored rules)
- Training data for learned models

Domain-agnostic — works for any signal type in any domain.
"""

from __future__ import annotations

import abc
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SignalOutcome(StrEnum):
    """What happened after a signal was surfaced."""

    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    ACTED_ON = "acted_on"
    ESCALATED = "escalated"
    FALSE_POSITIVE = "false_positive"


class SignalFeedback(BaseModel, frozen=True):
    """A single feedback event for a signal."""

    feedback_id: str
    signal_id: str
    signal_type: str
    outcome: SignalOutcome
    actor: str = ""
    notes: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime = Field(default_factory=_utcnow)


class SignalFeedbackSummary(BaseModel, frozen=True):
    """Aggregated feedback stats for a signal type."""

    signal_type: str
    total_feedback: int = 0
    outcome_counts: dict[str, int] = Field(default_factory=dict)
    act_rate: float = 0.0
    dismiss_rate: float = 0.0


class FeedbackStore(abc.ABC):
    """Read/write access to signal feedback data."""

    @abc.abstractmethod
    async def record_feedback(self, feedback: SignalFeedback) -> None:
        ...

    @abc.abstractmethod
    async def get_feedback(self, feedback_id: str) -> SignalFeedback | None:
        ...

    @abc.abstractmethod
    async def list_feedback(
        self,
        *,
        signal_id: str | None = None,
        signal_type: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[SignalFeedback]:
        ...

    @abc.abstractmethod
    async def summarize(self, signal_type: str) -> SignalFeedbackSummary:
        ...
