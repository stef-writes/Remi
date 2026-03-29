"""Tests for NoopEmbedder — deterministic hashing, normalization, dimension."""

from __future__ import annotations

import math

import pytest

from remi.infrastructure.vectors.embedder import NoopEmbedder


@pytest.fixture
def embedder() -> NoopEmbedder:
    return NoopEmbedder(dimension=64)


class TestNoopEmbedder:
    @pytest.mark.asyncio
    async def test_dimension(self, embedder: NoopEmbedder) -> None:
        assert embedder.dimension == 64

    @pytest.mark.asyncio
    async def test_embed_one_returns_correct_length(self, embedder: NoopEmbedder) -> None:
        vec = await embedder.embed_one("hello world")
        assert len(vec) == 64

    @pytest.mark.asyncio
    async def test_deterministic(self, embedder: NoopEmbedder) -> None:
        v1 = await embedder.embed_one("test input")
        v2 = await embedder.embed_one("test input")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_different_inputs_different_vectors(self, embedder: NoopEmbedder) -> None:
        v1 = await embedder.embed_one("alpha")
        v2 = await embedder.embed_one("beta")
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_unit_normalized(self, embedder: NoopEmbedder) -> None:
        vec = await embedder.embed_one("normalize me")
        norm = math.sqrt(sum(x * x for x in vec))
        assert norm == pytest.approx(1.0, abs=1e-6)

    @pytest.mark.asyncio
    async def test_batch_embed(self, embedder: NoopEmbedder) -> None:
        texts = ["one", "two", "three"]
        results = await embedder.embed(texts)
        assert len(results) == 3
        assert all(len(v) == 64 for v in results)

    @pytest.mark.asyncio
    async def test_embed_empty_list(self, embedder: NoopEmbedder) -> None:
        results = await embedder.embed([])
        assert results == []
