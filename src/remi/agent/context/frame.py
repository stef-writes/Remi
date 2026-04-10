"""ContextFrame — the agent's typed perception of its world.

The frame separates two concerns:

- **WorldState** (schema shape): static domain knowledge — what entity types,
  relationships, and processes the agent operates with.  Set once at priming.

- **ContextFrame** (per-turn): entities, graph neighborhood, and document
  context assembled by the ContextBuilder each turn.

Both stay typed until the injection boundary, where rendering projects
them into prose for the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from remi.agent.graph.retrieval.retriever import ResolvedEntity
from remi.agent.graph.types import KnowledgeLink
from remi.agent.signals import DomainSchema


@dataclass(frozen=True)
class WorldState:
    """Static schema shape — the dimensions of the agent's domain knowledge.

    Computed once from DomainSchema at priming time.  Immutable for the
    lifetime of the agent session.
    """

    entity_types: int = 0
    relationships: int = 0
    processes: int = 0

    @property
    def loaded(self) -> bool:
        return self.entity_types > 0

    @classmethod
    def from_schema(cls, domain: DomainSchema | None) -> WorldState:
        if domain is None:
            return cls()
        return cls(
            entity_types=len(getattr(domain, "entity_types", [])),
            relationships=len(getattr(domain, "relationships", [])),
            processes=len(getattr(domain, "processes", [])),
        )

    # Keep old name working during transition
    @classmethod
    def from_tbox(cls, domain: DomainSchema | None) -> WorldState:
        return cls.from_schema(domain)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_loaded": self.loaded,
            "entity_types": self.entity_types,
            "relationships": self.relationships,
            "processes": self.processes,
        }


@dataclass
class ContextFrame:
    """The agent's typed perception of its world.

    Contains entities, graph neighborhood, pre-fetched operational views,
    and document context assembled by the ContextBuilder each turn.

    ``world`` holds structured schema shape data.
    The schema itself lives in the agent's priming (system prompt).

    ``operational_context`` is keyed by entity_id and populated by the
    injected EntityViewEnricher (application layer). Each value is a
    rendered, token-budgeted summary of that entity's live data — enough
    for the LLM to answer most questions without tool calls.
    """

    world: WorldState = field(default_factory=WorldState)

    entities: list[ResolvedEntity] = field(default_factory=list)
    neighborhood: dict[str, list[KnowledgeLink]] = field(default_factory=dict)

    operational_context: dict[str, str] = field(default_factory=dict)
    document_context: str = ""
    question: str | None = None
