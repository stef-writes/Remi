"""Hypothesis models — candidate TBox entries awaiting review."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from remi.models.signals.enums import HypothesisKind, HypothesisStatus


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Hypothesis(BaseModel, frozen=True):
    """A candidate law discovered from data patterns.

    Not a signal — a proposed addition to the domain's known physics.
    Must be confirmed before it affects signal production.
    """

    hypothesis_id: str
    kind: HypothesisKind
    title: str
    description: str
    status: HypothesisStatus = HypothesisStatus.PROPOSED

    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = 0
    evidence: dict[str, Any] = Field(default_factory=dict)

    proposed_by: str = ""
    proposed_at: datetime = Field(default_factory=_utcnow)
    reviewed_by: str = ""
    reviewed_at: datetime | None = None
    review_notes: str = ""

    proposed_tbox_entry: dict[str, Any] = Field(default_factory=dict)
