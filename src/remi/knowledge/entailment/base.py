"""Shared types for the entailment engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from remi.models.signals import Signal, SignalDefinition


class MakeSignalFn(Protocol):
    """Callable that builds a Signal from evaluated evidence."""

    def __call__(
        self,
        *,
        defn: SignalDefinition,
        entity_id: str,
        entity_name: str,
        description: str,
        evidence: dict[str, Any],
    ) -> Signal: ...


@dataclass
class EntailmentResult:
    """Result type for ``EntailmentEngine.run_all()``.

    The composite pipeline uses ``CompositeResult`` instead; this type is
    specific to the rule-based engine's direct ``run_all()`` path.
    """

    produced: int = 0
    retired: int = 0
    unchanged: int = 0
    signals: list[Signal] = field(default_factory=list)
    trace_id: str | None = None


def signal_id(signal_type: str, entity_id: str) -> str:
    return f"signal:{signal_type.lower()}:{entity_id}"
