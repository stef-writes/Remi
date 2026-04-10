"""Graph-aware entity retrieval — fuses vector similarity with link expansion.

Given a user question, resolves relevant entities via vector search
(with a keyword fallback for named-entity lookups), then expands
through the WorldModel to pull in related context.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from remi.agent.graph.stores import WorldModel
from remi.agent.graph.types import KnowledgeLink
from remi.agent.observe.events import Event
from remi.agent.vectors.types import Embedder, SearchResult, VectorStore

_DEFAULT_NAME_FIELDS: tuple[str, ...] = ("name",)

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ResolvedEntity:
    """An entity resolved from the question with its graph neighborhood."""

    entity_id: str
    entity_type: str
    properties: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class RetrievalResult:
    """Output of graph-aware retrieval."""

    entities: list[ResolvedEntity] = field(default_factory=list)
    neighborhood: dict[str, list[KnowledgeLink]] = field(default_factory=dict)


class GraphRetriever:
    """Resolves entities relevant to a question via vector + WorldModel link expansion."""

    def __init__(
        self,
        world_model: WorldModel | None = None,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        name_fields: tuple[str, ...] | None = None,
    ) -> None:
        self._world = world_model
        self._vs = vector_store
        self._embedder = embedder
        self._name_fields = name_fields or _DEFAULT_NAME_FIELDS

    async def retrieve(
        self,
        question: str,
        *,
        max_entities: int = 10,
        expand_depth: int = 1,
        link_type_filter: set[str] | None = None,
        entity_type_filter: set[str] | None = None,
    ) -> RetrievalResult:
        """Resolve entities from the question and expand through WorldModel links.

        ``expand_depth``: how many hops to expand (1 = direct neighbors).
        ``link_type_filter``: only follow these link types during expansion.
        ``entity_type_filter``: only include neighbors of these entity types.
        """
        result = RetrievalResult()

        resolved = await self._resolve_entities(question, max_entities=max_entities)
        result.entities = resolved

        if self._world is None or expand_depth < 1:
            return result

        for entity in resolved:
            try:
                links = await self._world.get_links(entity.entity_id)
                filtered: list[KnowledgeLink] = []
                for gl in links:
                    if link_type_filter and gl.link_type not in link_type_filter:
                        continue
                    target_type = gl.properties.get("target_type", "")
                    if entity_type_filter and target_type and target_type not in entity_type_filter:
                        continue
                    filtered.append(
                        KnowledgeLink(
                            source_id=gl.source_id,
                            link_type=gl.link_type,
                            target_id=gl.target_id,
                            properties=gl.properties,
                        )
                    )
                result.neighborhood[entity.entity_id] = filtered
            except Exception:
                _log.warning(
                    Event.GRAPH_EXPAND_FAILED,
                    entity_id=entity.entity_id,
                    exc_info=True,
                )

        await self._enrich_neighborhood(result)

        return result

    async def _enrich_neighborhood(self, result: RetrievalResult) -> None:
        """Fetch key scalars for each link target and store them in link.properties.

        Converts bare ``→ HAS_LEASE → lease-abc`` references into
        ``→ HAS_LEASE → lease-abc (end_date=2025-06-30, monthly_rent=2400)``
        so the LLM can reason about neighbors without an extra tool call.
        """
        if self._world is None:
            return

        all_target_ids: set[str] = set()
        for links in result.neighborhood.values():
            for link in links:
                all_target_ids.add(link.target_id)

        seed_ids = {e.entity_id for e in result.entities}
        fetch_ids = all_target_ids - seed_ids

        if not fetch_ids:
            return

        objects = await asyncio.gather(
            *[self._world.get_object(tid) for tid in fetch_ids],
            return_exceptions=True,
        )
        scalars: dict[str, dict[str, object]] = {}
        for obj in objects:
            if isinstance(obj, Exception) or obj is None:
                continue
            scalars[obj.id] = _extract_key_scalars(obj.properties)

        if not scalars:
            return

        for entity_id, links in result.neighborhood.items():
            result.neighborhood[entity_id] = [
                KnowledgeLink(
                    source_id=lk.source_id,
                    link_type=lk.link_type,
                    target_id=lk.target_id,
                    properties={**lk.properties, **scalars.get(lk.target_id, {})},
                )
                for lk in links
            ]

    async def _resolve_entities(
        self,
        question: str,
        *,
        max_entities: int = 10,
    ) -> list[ResolvedEntity]:
        """Find entities via keyword name match then vector similarity, merged."""
        if self._vs is None or self._embedder is None:
            return []

        seen_ids: set[str] = set()
        entities: list[ResolvedEntity] = []

        keyword_hits = await self._keyword_resolve(question, limit=max_entities)
        for r in keyword_hits:
            if r.entity_id not in seen_ids:
                seen_ids.add(r.entity_id)
                entities.append(
                    ResolvedEntity(
                        entity_id=r.entity_id,
                        entity_type=r.entity_type,
                        properties={"text": r.text, **r.record.metadata},
                        score=r.score,
                    )
                )

        remaining = max_entities - len(entities)
        if remaining > 0:
            try:
                query_vector = await self._embedder.embed_one(question)
                results: list[SearchResult] = await self._vs.search(
                    query_vector,
                    limit=remaining,
                    min_score=0.15,
                )
            except Exception:
                _log.warning(Event.VECTOR_SEARCH_FAILED, exc_info=True)
                results = []

            for r in results:
                if r.entity_id not in seen_ids:
                    seen_ids.add(r.entity_id)
                    entities.append(
                        ResolvedEntity(
                            entity_id=r.entity_id,
                            entity_type=r.entity_type,
                            properties={"text": r.text, **r.record.metadata},
                            score=r.score,
                        )
                    )

        return entities

    async def _keyword_resolve(
        self,
        question: str,
        *,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Try to match entity names mentioned in the question via metadata scan."""
        if self._vs is None:
            return []

        candidates = _extract_name_candidates(question)
        if not candidates:
            return []

        seen: set[str] = set()
        results: list[SearchResult] = []
        for candidate in candidates:
            hits = await self._vs.metadata_text_search(
                candidate,
                fields=list(self._name_fields),
                limit=limit,
            )
            for hit in hits:
                if hit.entity_id not in seen:
                    seen.add(hit.entity_id)
                    results.append(hit)
            if len(results) >= limit:
                break
        return results[:limit]


_SCALAR_PRIORITY: tuple[str, ...] = (
    "name",
    "status",
    "end_date",
    "start_date",
    "monthly_rent",
    "market_rent",
    "balance_owed",
    "unit_number",
    "address",
    "email",
)
_MAX_SCALAR_FIELDS = 4


def _extract_key_scalars(props: dict[str, Any]) -> dict[str, object]:
    """Return the most informative scalar fields from an entity's properties.

    Picks from a priority list first, then any remaining scalars up to
    ``_MAX_SCALAR_FIELDS``. Non-scalar values (lists, dicts) are skipped.
    """
    result: dict[str, object] = {}
    for key in _SCALAR_PRIORITY:
        val = props.get(key)
        if val is not None and isinstance(val, (str, int, float, bool)):
            result[key] = val
            if len(result) >= _MAX_SCALAR_FIELDS:
                return result
    for key, val in props.items():
        if key in result or key == "id":
            continue
        if isinstance(val, (str, int, float, bool)) and val is not None:
            result[key] = val
            if len(result) >= _MAX_SCALAR_FIELDS:
                break
    return result


def _extract_name_candidates(question: str) -> list[str]:
    """Extract potential entity names from a question.

    Returns candidates longest-first so that "Jake Kraus" is tried
    before "Jake" alone.
    """
    words = question.split()
    candidates: list[str] = []

    for length in range(min(4, len(words)), 1, -1):
        for i in range(len(words) - length + 1):
            segment = " ".join(words[i : i + length])
            cleaned = re.sub(r"[^\w\s]", "", segment).strip()
            if not cleaned or len(cleaned) < 3:
                continue
            if all(w[0].isupper() for w in cleaned.split() if w):
                candidates.append(cleaned)

    for word in words:
        cleaned = re.sub(r"[^\w]", "", word).strip()
        if len(cleaned) >= 3 and cleaned[0].isupper():
            candidates.append(cleaned)

    seen: set[str] = set()
    deduped: list[str] = []
    for c in candidates:
        lower = c.lower()
        if lower not in seen:
            seen.add(lower)
            deduped.append(c)
    return deduped
