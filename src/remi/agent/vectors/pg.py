"""Postgres-backed VectorStore using JSON-stored vectors with application-level similarity.

For production at scale, swap the vector column to ``pgvector`` and use
``<=>`` cosine distance in SQL. This adapter keeps the interface identical
to ``InMemoryVectorStore`` so the swap is transparent.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from remi.agent.db.tables import VectorEmbeddingRow
from remi.agent.vectors.types import EmbeddingRecord, SearchResult, VectorStore

_log = structlog.get_logger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _record_to_row(record: EmbeddingRecord) -> VectorEmbeddingRow:
    return VectorEmbeddingRow(
        id=record.id,
        text=record.text,
        source_entity_id=record.source_entity_id,
        source_entity_type=record.source_entity_type,
        source_field=record.source_field,
        metadata_=record.metadata,
        vector=record.vector,
        created_at=record.created_at,
    )


def _row_to_record(row: VectorEmbeddingRow) -> EmbeddingRecord:
    return EmbeddingRecord(
        id=row.id,
        text=row.text,
        vector=row.vector or [],
        source_entity_id=row.source_entity_id,
        source_entity_type=row.source_entity_type,
        source_field=row.source_field,
        metadata=row.metadata_ or {},
        created_at=row.created_at,
    )


class PostgresVectorStore(VectorStore):
    """Postgres-backed vector store with application-level cosine similarity."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def put(self, record: EmbeddingRecord) -> None:
        async with self._sf() as session:
            existing = await session.get(VectorEmbeddingRow, record.id)
            if existing is not None:
                existing.text = record.text
                existing.vector = record.vector
                existing.source_entity_id = record.source_entity_id
                existing.source_entity_type = record.source_entity_type
                existing.source_field = record.source_field
                existing.metadata_ = record.metadata
                session.add(existing)
            else:
                session.add(_record_to_row(record))
            await session.commit()

    async def put_many(self, records: list[EmbeddingRecord]) -> None:
        async with self._sf() as session:
            for record in records:
                existing = await session.get(VectorEmbeddingRow, record.id)
                if existing is not None:
                    existing.text = record.text
                    existing.vector = record.vector
                    existing.source_entity_id = record.source_entity_id
                    existing.source_entity_type = record.source_entity_type
                    existing.source_field = record.source_field
                    existing.metadata_ = record.metadata
                    session.add(existing)
                else:
                    session.add(_record_to_row(record))
            await session.commit()

    async def search(
        self,
        query_vector: list[float],
        *,
        limit: int = 10,
        entity_type: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        async with self._sf() as session:
            stmt = select(VectorEmbeddingRow)
            if entity_type is not None:
                stmt = stmt.where(
                    col(VectorEmbeddingRow.source_entity_type) == entity_type,
                )
            result = await session.exec(stmt)
            rows = result.all()

        scored: list[SearchResult] = []
        for row in rows:
            record = _row_to_record(row)
            if metadata_filter and not all(
                record.metadata.get(k) == v for k, v in metadata_filter.items()
            ):
                continue
            score = _cosine_similarity(query_vector, record.vector)
            if score >= min_score:
                scored.append(SearchResult(record=record, score=round(score, 6)))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]

    async def get(self, record_id: str) -> EmbeddingRecord | None:
        async with self._sf() as session:
            row = await session.get(VectorEmbeddingRow, record_id)
            return _row_to_record(row) if row else None

    async def delete(self, record_id: str) -> None:
        async with self._sf() as session:
            row = await session.get(VectorEmbeddingRow, record_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def delete_by_source(self, source_entity_id: str) -> None:
        async with self._sf() as session:
            stmt = select(VectorEmbeddingRow).where(
                col(VectorEmbeddingRow.source_entity_id) == source_entity_id,
            )
            result = await session.exec(stmt)
            for row in result.all():
                await session.delete(row)
            await session.commit()

    async def count(self) -> int:
        async with self._sf() as session:
            from sqlalchemy import func
            stmt = select(func.count()).select_from(VectorEmbeddingRow)
            result = await session.exec(stmt)
            return result.one()

    async def stats(self) -> dict[str, int]:
        async with self._sf() as session:
            stmt = select(VectorEmbeddingRow)
            result = await session.exec(stmt)
            counts: dict[str, int] = defaultdict(int)
            for row in result.all():
                counts[row.source_entity_type] += 1
            return dict(counts)

    async def metadata_text_search(
        self,
        query: str,
        *,
        fields: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not query:
            return []
        async with self._sf() as session:
            stmt = select(VectorEmbeddingRow)
            result = await session.exec(stmt)
            rows = result.all()

        query_lower = query.lower()
        results: list[SearchResult] = []
        for row in rows:
            record = _row_to_record(row)
            for key, value in record.metadata.items():
                if fields and key not in fields:
                    continue
                if isinstance(value, str) and query_lower in value.lower():
                    results.append(SearchResult(record=record, score=1.0))
                    break
            if len(results) >= limit:
                break
        return results
