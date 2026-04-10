"""EntityViewEnricher — protocol for pre-fetching application views into context.

Application layer implements this. The kernel calls it after entity resolution
to pre-populate the ContextFrame with structured data so the LLM can answer
common questions without making tool calls.

Design:
- Protocol-only. Zero application imports. Injected from shell/container.py.
- Returns rendered strings, not raw model objects — the kernel renders prose,
  not domain types.
- Implementations should be token-budget-aware: return condensed summaries,
  not full data dumps.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from remi.agent.graph.retrieval.retriever import ResolvedEntity


@runtime_checkable
class EntityViewEnricher(Protocol):
    """Pre-fetch structured application views for resolved entities.

    Called by ContextBuilder after GraphRetriever resolves entities.
    Returns a dict mapping entity_id → rendered context string.

    Only entities the implementation recognises (by entity_type) need a
    returned entry; unknown entity types are silently skipped.
    """

    async def enrich(
        self,
        entities: list[ResolvedEntity],
    ) -> dict[str, str]: ...
