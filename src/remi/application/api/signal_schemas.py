"""Signal API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from remi.agent.signals.feedback import SignalFeedback


class SignalSummary(BaseModel, frozen=True):
    signal_id: str
    signal_type: str
    severity: str
    entity_type: str
    entity_id: str
    entity_name: str
    description: str
    detected_at: str


class SignalListResponse(BaseModel, frozen=True):
    count: int
    signals: list[SignalSummary]


class SignalDetailResponse(SignalSummary, frozen=True):
    pass


class SignalExplainResponse(SignalSummary, frozen=True):
    provenance: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class SourceResult(BaseModel, frozen=True):
    produced: int
    errors: int


class EntailmentResponse(BaseModel, frozen=True):
    produced: int
    signal_count: int
    sources: dict[str, SourceResult]
    trace_id: str | None = None


class FeedbackRequest(BaseModel):
    outcome: str = "acknowledged"
    actor: str = ""
    notes: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class FeedbackResponse(BaseModel, frozen=True):
    ok: bool = True
    feedback_id: str
    signal_id: str
    outcome: str


class FeedbackListResponse(BaseModel, frozen=True):
    signal_id: str
    count: int
    feedback: list[SignalFeedback]


class FeedbackSummaryResponse(BaseModel):
    """Wraps the feedback summary model_dump output."""

    total: int = 0
    by_outcome: dict[str, int] = Field(default_factory=dict)
