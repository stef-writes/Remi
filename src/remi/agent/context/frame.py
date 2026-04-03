"""ContextFrame — the agent's typed perception of its world.

The frame separates two concerns:

- **WorldState** (TBox shape): static domain knowledge — how many signal
  definitions, thresholds, policies, and causal chains the agent operates
  with.  This is set once at agent priming time and does not change per turn.

- **PerceptionSnapshot** (ABox state): the current situational awareness —
  active signal counts, severity distribution, compounding situations.
  This is assembled fresh each turn by the ContextBuilder.

Both stay typed until the injection boundary, where rendering projects
them into prose for the LLM.  Before that point, any code (runtime,
tools, CLI) can inspect the structured data directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from remi.agent.graph.retriever import ResolvedEntity
from remi.agent.graph.types import KnowledgeLink
from remi.agent.signals import CausalChain, DomainTBox, MutableTBox, Policy, Signal


@dataclass(frozen=True)
class WorldState:
    """Static TBox shape — the dimensions of the agent's domain knowledge.

    Computed once from DomainTBox at priming time.  Immutable for the
    lifetime of the agent session.
    """

    signal_definitions: int = 0
    thresholds: int = 0
    policies: int = 0
    causal_chains: int = 0
    compositions: int = 0

    @property
    def loaded(self) -> bool:
        return self.signal_definitions > 0

    @classmethod
    def from_tbox(cls, domain: DomainTBox | MutableTBox | None) -> WorldState:
        if domain is None:
            return cls()
        return cls(
            signal_definitions=len(getattr(domain, "signals", {})),
            thresholds=len(getattr(domain, "thresholds", {})),
            policies=len(getattr(domain, "policies", [])),
            causal_chains=len(getattr(domain, "causal_chains", [])),
            compositions=len(getattr(domain, "compositions", [])),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "tbox_loaded": self.loaded,
            "signal_definitions": self.signal_definitions,
            "thresholds": self.thresholds,
            "policies": self.policies,
            "causal_chains": self.causal_chains,
            "compositions": self.compositions,
        }


@dataclass(frozen=True)
class CompoundingSituation:
    """A composition rule that is currently firing."""

    name: str
    severity: str
    constituents: list[str]
    entity_ids: list[str]


@dataclass
class PerceptionSnapshot:
    """Current ABox situational awareness — what's happening right now.

    Assembled fresh each turn by the ContextBuilder from the signal store.
    """

    active_signals: int = 0
    severity_counts: dict[str, int] = field(default_factory=dict)
    compounding: list[CompoundingSituation] = field(default_factory=list)

    @property
    def severity_breakdown(self) -> dict[str, int]:
        """Severity counts in canonical worst-to-best order."""
        order = ["critical", "high", "medium", "low"]
        return {s: self.severity_counts[s] for s in order if self.severity_counts.get(s)}

    def to_dict(self) -> dict[str, object]:
        return {
            "active_signals": self.active_signals,
            "severity": self.severity_breakdown,
            "compounding": [
                {"name": c.name, "severity": c.severity, "constituents": c.constituents}
                for c in self.compounding
            ],
        }


@dataclass
class ContextFrame:
    """The agent's typed perception of its world.

    Contains everything the agent needs to reason — entities, signals,
    policies, causal chains, and graph neighborhood — without making
    tool calls to discover it.

    ``world`` and ``perception`` hold structured data that stays typed
    until the injection boundary.  ``signal_summary`` is the rendered
    prose projection of ABox perception, filled at injection time.
    The TBox is not here — it lives in the agent's priming (system prompt).
    """

    # Typed perception (structured, inspectable)
    world: WorldState = field(default_factory=WorldState)
    perception: PerceptionSnapshot = field(default_factory=PerceptionSnapshot)

    # Detailed data
    entities: list[ResolvedEntity] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    policies: list[Policy] = field(default_factory=list)
    causal_chains: list[CausalChain] = field(default_factory=list)
    neighborhood: dict[str, list[KnowledgeLink]] = field(default_factory=dict)

    # Rendered ABox prose (filled at injection boundary)
    signal_summary: str = ""
    question: str | None = None
