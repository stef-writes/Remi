"""Tests for InMemoryVectorStore — CRUD, search, filtering, cosine similarity."""

from __future__ import annotations

import math

import pytest

from remi.domain.retrieval.types import EmbeddingRecord
from remi.infrastructure.vectors.in_memory import InMemoryVectorStore, _cosine_similarity


@pytest.fixture
def store() -> InMemoryVectorStore:
    return InMemoryVectorStore()


def _make_record(
    id: str,
    vector: list[float],
    entity_id: str = "ent-1",
    entity_type: str = "Tenant",
    text: str = "test",
    **metadata: str,
) -> EmbeddingRecord:
    return EmbeddingRecord(
        id=id,
        text=text,
        vector=vector,
        source_entity_id=entity_id,
        source_entity_type=entity_type,
        source_field="profile",
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Cosine similarity function
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_different_lengths_returns_zero(self) -> None:
        assert _cosine_similarity([1.0], [1.0, 2.0]) == 0.0

    def test_zero_vector_returns_zero(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


class TestCRUD:
    @pytest.mark.asyncio
    async def test_put_and_get(self, store: InMemoryVectorStore) -> None:
        rec = _make_record("r1", [1.0, 0.0])
        await store.put(rec)
        assert await store.get("r1") == rec

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, store: InMemoryVectorStore) -> None:
        assert await store.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_put_many(self, store: InMemoryVectorStore) -> None:
        records = [_make_record(f"r{i}", [float(i)]) for i in range(5)]
        await store.put_many(records)
        assert await store.count() == 5

    @pytest.mark.asyncio
    async def test_delete(self, store: InMemoryVectorStore) -> None:
        await store.put(_make_record("r1", [1.0]))
        await store.delete("r1")
        assert await store.get("r1") is None
        assert await store.count() == 0

    @pytest.mark.asyncio
    async def test_delete_by_source(self, store: InMemoryVectorStore) -> None:
        await store.put(_make_record("r1", [1.0], entity_id="ent-A"))
        await store.put(_make_record("r2", [2.0], entity_id="ent-A"))
        await store.put(_make_record("r3", [3.0], entity_id="ent-B"))
        await store.delete_by_source("ent-A")
        assert await store.count() == 1
        assert await store.get("r3") is not None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    @pytest.mark.asyncio
    async def test_basic_search_returns_sorted(self, store: InMemoryVectorStore) -> None:
        v_close = [1.0, 0.1, 0.0]
        v_far = [0.0, 1.0, 0.0]
        await store.put(_make_record("close", v_close))
        await store.put(_make_record("far", v_far))

        query = [1.0, 0.0, 0.0]
        results = await store.search(query, limit=10)
        assert len(results) == 2
        assert results[0].record.id == "close"
        assert results[0].score > results[1].score

    @pytest.mark.asyncio
    async def test_entity_type_filter(self, store: InMemoryVectorStore) -> None:
        await store.put(_make_record("t1", [1.0, 0.0], entity_type="Tenant"))
        await store.put(_make_record("u1", [1.0, 0.0], entity_type="Unit"))

        results = await store.search([1.0, 0.0], entity_type="Tenant")
        assert len(results) == 1
        assert results[0].entity_type == "Tenant"

    @pytest.mark.asyncio
    async def test_metadata_filter(self, store: InMemoryVectorStore) -> None:
        await store.put(_make_record("r1", [1.0], manager_id="mgr-1"))
        await store.put(_make_record("r2", [1.0], manager_id="mgr-2"))

        results = await store.search(
            [1.0], metadata_filter={"manager_id": "mgr-1"},
        )
        assert len(results) == 1
        assert results[0].record.metadata["manager_id"] == "mgr-1"

    @pytest.mark.asyncio
    async def test_min_score_filter(self, store: InMemoryVectorStore) -> None:
        await store.put(_make_record("close", [1.0, 0.0]))
        await store.put(_make_record("far", [0.0, 1.0]))

        results = await store.search([1.0, 0.0], min_score=0.9)
        assert len(results) == 1
        assert results[0].record.id == "close"

    @pytest.mark.asyncio
    async def test_limit(self, store: InMemoryVectorStore) -> None:
        for i in range(20):
            await store.put(_make_record(f"r{i}", [1.0, float(i) / 100]))
        results = await store.search([1.0, 0.0], limit=5)
        assert len(results) == 5


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    @pytest.mark.asyncio
    async def test_stats_empty(self, store: InMemoryVectorStore) -> None:
        assert await store.stats() == {}
        assert await store.count() == 0

    @pytest.mark.asyncio
    async def test_stats_grouped(self, store: InMemoryVectorStore) -> None:
        await store.put(_make_record("t1", [1.0], entity_type="Tenant"))
        await store.put(_make_record("t2", [1.0], entity_type="Tenant"))
        await store.put(_make_record("u1", [1.0], entity_type="Unit"))

        s = await store.stats()
        assert s == {"Tenant": 2, "Unit": 1}
