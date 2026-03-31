"""Runtime ABox signal model and producer protocol."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from remi.models.ontology import KnowledgeProvenance as Provenance

if TYPE_CHECKING:
    from remi.models.signals.enums import Severity


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Signal(BaseModel, frozen=True):
    """A named, evidenced, severity-ranked entailed state.

    Produced by a SignalProducer (rule engine, statistical detector, or
    learned model) when its evaluation criteria are met against ABox facts.

    ``entity_type`` accepts any string — EntityType enum values for RE,
    arbitrary strings for custom domains.
    """

    signal_id: str
    signal_type: str
    severity: Severity
    entity_type: str
    entity_id: str
    entity_name: str = ""
    description: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime = Field(default_factory=_utcnow)
    provenance: Provenance = Provenance.DATA_DERIVED  # type: ignore[assignment]


@dataclass
class ProducerResult:
    """Output of a single producer run."""

    signals: list[Signal] = field(default_factory=list)
    produced: int = 0
    errors: int = 0
    source: str = ""


class SignalProducer(abc.ABC):
    """Anything that can evaluate facts and produce signals."""

    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @abc.abstractmethod
    async def evaluate(self) -> ProducerResult: ...
