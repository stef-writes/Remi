"""Signal feedback models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from remi.models.signals.enums import SignalOutcome


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
