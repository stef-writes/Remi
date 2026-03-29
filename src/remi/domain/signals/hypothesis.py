"""Hypothesis — a candidate TBox entry proposed by induction.

The knowledge architecture has three reasoning modes:

- **Deduction** (rule engine): known law + observed fact → predicted signal.
  Certain. Auditable. The physics textbook applied.

- **Induction** (pattern detector): observed patterns → candidate law.
  Probabilistic. Requires confirmation. This is what Hypothesis represents.

- **Abduction** (LLM): observed signals → best explanation.
  The scientist interpreting results. Not formalized here.

A Hypothesis is NOT a signal. It is a proposed addition to the TBox —
a candidate signal definition, causal chain, threshold adjustment, or
new object type relationship. It must be reviewed and confirmed before
it becomes part of the domain's known physics.

Lifecycle:
    PROPOSED → CONFIRMED → graduated into TBox (SignalDefinition, CausalChain, etc.)
    PROPOSED → REJECTED  → archived with reason
    PROPOSED → EXPIRED   → too old, never reviewed
"""

from __future__ import annotations

import abc
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class HypothesisKind(StrEnum):
    """What kind of TBox entry this hypothesis proposes."""

    SIGNAL_DEFINITION = "signal_definition"
    CAUSAL_CHAIN = "causal_chain"
    THRESHOLD_ADJUSTMENT = "threshold_adjustment"
    CORRELATION = "correlation"
    ANOMALY_PATTERN = "anomaly_pattern"


class HypothesisStatus(StrEnum):
    """Lifecycle state of a hypothesis."""

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


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
