"""In-memory vector store with brute-force cosine similarity.

Good for development and small-to-medium datasets (< 100k records).
Production deployments should swap for pgvector or a dedicated service.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from remi.domain.retrieval.ports import VectorStore
from remi.domain.retrieval.types import EmbeddingRecord, SearchResult


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryVectorStore(VectorStore):

    def __init__(self) -> None:
        self._records: dict[str, EmbeddingRecord] = {}
        self._by_source: dict[str, set[str]] = defaultdict(set)

    async def put(self, record: EmbeddingRecord) -> None:
        self._records[record.id] = record
        self._by_source[record.source_entity_id].add(record.id)

    async def put_many(self, records: list[EmbeddingRecord]) -> None:
        for record in records:
            await self.put(record)

    async def search(
        self,
        query_vector: list[float],
        *,
        limit: int = 10,
        entity_type: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        candidates = list(self._records.values())

        if entity_type is not None:
            candidates = [r for r in candidates if r.source_entity_type == entity_type]

        if metadata_filter:
            filtered = []
            for r in candidates:
                match = all(
                    r.metadata.get(k) == v
                    for k, v in metadata_filter.items()
                )
                if match:
                    filtered.append(r)
            candidates = filtered

        scored: list[SearchResult] = []
        for record in candidates:
            score = _cosine_similarity(query_vector, record.vector)
            if score >= min_score:
                scored.append(SearchResult(record=record, score=round(score, 6)))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]

    async def get(self, record_id: str) -> EmbeddingRecord | None:
        return self._records.get(record_id)

    async def delete(self, record_id: str) -> None:
        record = self._records.pop(record_id, None)
        if record is not None:
            source_set = self._by_source.get(record.source_entity_id)
            if source_set:
                source_set.discard(record_id)

    async def delete_by_source(self, source_entity_id: str) -> None:
        record_ids = self._by_source.pop(source_entity_id, set())
        for rid in record_ids:
            self._records.pop(rid, None)

    async def count(self) -> int:
        return len(self._records)

    async def stats(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for record in self._records.values():
            counts[record.source_entity_type] += 1
        return dict(counts)
