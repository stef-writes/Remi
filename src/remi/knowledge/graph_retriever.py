"""Graph-aware entity retrieval — fuses vector similarity with graph traversal.

Given a user question, resolves relevant entities via vector search
(with a keyword fallback for named-entity lookups), then expands
through the knowledge graph to pull in related context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from remi.models.ontology import KnowledgeLink, KnowledgeGraph
from remi.models.retrieval import Embedder, SearchResult, VectorStore
from remi.models.signals import Signal, SignalStore
from remi.observability.events import Event

_NAME_FIELDS = ("tenant_name", "property_name", "manager_name")

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
    signals: list[Signal] = field(default_factory=list)
    neighborhood: dict[str, list[KnowledgeLink]] = field(default_factory=dict)


class GraphRetriever:
    """Resolves entities relevant to a question via vector + graph traversal."""

    def __init__(
        self,
        knowledge_graph: KnowledgeGraph,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        signal_store: SignalStore | None = None,
    ) -> None:
        self._kg = knowledge_graph
        self._vs = vector_store
        self._embedder = embedder
        self._ss = signal_store

    async def retrieve(
        self,
        question: str,
        *,
        max_entities: int = 10,
        expand_depth: int = 1,
    ) -> RetrievalResult:
        """Resolve entities from the question and expand through the graph."""
        result = RetrievalResult()

        resolved = await self._resolve_entities(question, max_entities=max_entities)
        result.entities = resolved

        for entity in resolved:
            if expand_depth > 0:
                try:
                    raw_links = await self._kg.get_links(entity.entity_id, direction="both")
                    typed_links: list[KnowledgeLink] = []
                    for raw in raw_links if isinstance(raw_links, list) else []:
                        if isinstance(raw, KnowledgeLink):
                            typed_links.append(raw)
                        elif isinstance(raw, dict):
                            typed_links.append(
                                KnowledgeLink(
                                    source_id=raw.get("source_id", entity.entity_id),
                                    link_type=raw.get("link_type", raw.get("type", "")),
                                    target_id=raw.get("target_id", ""),
                                    properties={
                                        k: v
                                        for k, v in raw.items()
                                        if k not in ("source_id", "link_type", "target_id", "type")
                                    },
                                )
                            )
                    result.neighborhood[entity.entity_id] = typed_links
                except Exception:
                    _log.warning(Event.GRAPH_EXPAND_FAILED, entity_id=entity.entity_id, exc_info=True)

        if self._ss is not None:
            entity_ids = {e.entity_id for e in resolved}
            try:
                all_signals = await self._ss.list_signals()
                result.signals = [s for s in all_signals if s.entity_id in entity_ids]
            except Exception:
                _log.warning(Event.SIGNAL_RETRIEVAL_FAILED, exc_info=True)

        return result

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
                candidate, fields=list(_NAME_FIELDS), limit=limit,
            )
            for hit in hits:
                if hit.entity_id not in seen:
                    seen.add(hit.entity_id)
                    results.append(hit)
            if len(results) >= limit:
                break
        return results[:limit]


def _extract_name_candidates(question: str) -> list[str]:
    """Extract potential entity names from a question.

    Returns candidates longest-first so that "Alice Chen" is tried
    before "Alice" alone.
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
