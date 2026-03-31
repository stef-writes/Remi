"""Graph-aware entity retrieval — fuses vector similarity with graph traversal.

Given a user question, resolves relevant entities via vector search,
then expands through the knowledge graph to pull in related context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from remi.models.ontology import OntologyLink, OntologyStore
from remi.models.retrieval import Embedder, SearchResult, VectorStore
from remi.models.signals import Signal, SignalStore

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
    neighborhood: dict[str, list[OntologyLink]] = field(default_factory=dict)


class GraphRetriever:
    """Resolves entities relevant to a question via vector + graph traversal."""

    def __init__(
        self,
        ontology_store: OntologyStore,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        signal_store: SignalStore | None = None,
    ) -> None:
        self._onto = ontology_store
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
                    raw_links = await self._onto.get_links(entity.entity_id, direction="both")
                    typed_links: list[OntologyLink] = []
                    for raw in raw_links if isinstance(raw_links, list) else []:
                        if isinstance(raw, OntologyLink):
                            typed_links.append(raw)
                        elif isinstance(raw, dict):
                            typed_links.append(
                                OntologyLink(
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
                    _log.debug("graph_expand_failed", entity_id=entity.entity_id, exc_info=True)

        if self._ss is not None:
            entity_ids = {e.entity_id for e in resolved}
            try:
                all_signals = await self._ss.list_signals()
                result.signals = [s for s in all_signals if s.entity_id in entity_ids]
            except Exception:
                _log.debug("signal_retrieval_failed", exc_info=True)

        return result

    async def _resolve_entities(
        self,
        question: str,
        *,
        max_entities: int = 10,
    ) -> list[ResolvedEntity]:
        """Find entities relevant to the question via vector similarity."""
        if self._vs is None or self._embedder is None:
            return []

        try:
            query_vector = await self._embedder.embed_one(question)
            results: list[SearchResult] = await self._vs.search(
                query_vector,
                limit=max_entities,
                min_score=0.3,
            )
        except Exception:
            _log.debug("vector_search_failed", exc_info=True)
            return []

        entities: list[ResolvedEntity] = []
        for r in results:
            entities.append(
                ResolvedEntity(
                    entity_id=r.entity_id,
                    entity_type=r.entity_type,
                    properties={"text": r.text, **r.record.metadata},
                    score=r.score,
                )
            )

        return entities
