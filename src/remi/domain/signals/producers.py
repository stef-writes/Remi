"""SignalProducer port — the pluggable interface for signal sources.

Any component that can evaluate facts and produce signals implements this
ABC. The framework ships with:

- ``RuleBasedProducer`` — evaluates TBox rules against ABox facts (knowledge
  engineering, deterministic, auditable)
- ``StatisticalProducer`` — detects outliers, trends, and correlations from
  data in OntologyStore (data-driven, no hand-authored rules needed)
- ``CompositeProducer`` — runs multiple producers and merges their results

All producers share the same contract: facts in, typed ``Signal`` list out.
The ``provenance`` field on each Signal tracks which layer produced it.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remi.domain.signals.types import Signal


@dataclass
class ProducerResult:
    """Output of a single producer run.

    Tracks counts separately so the composite can report per-source stats.
    """

    signals: list[Signal] = field(default_factory=list)
    produced: int = 0
    errors: int = 0
    source: str = ""


class SignalProducer(abc.ABC):
    """Anything that can evaluate facts and produce signals.

    Implementations must:
    - Be async (data access is always async in REMI)
    - Return a ProducerResult with all signals and counts
    - Set ``provenance`` on each Signal to indicate the source layer
    - Be idempotent — calling evaluate() twice with the same state
      produces the same signals
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable name for this producer (used in logs and traces)."""
        ...

    @abc.abstractmethod
    async def evaluate(self) -> ProducerResult:
        """Run all evaluations and return produced signals."""
        ...
