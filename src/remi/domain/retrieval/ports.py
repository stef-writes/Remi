"""Retrieval ports — abstract interfaces for vector storage and embedding.

These ABCs define the contracts. Infrastructure provides implementations
(in-memory, pgvector, Pinecone, etc. for VectorStore; OpenAI,
sentence-transformers, etc. for Embedder).
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from remi.domain.retrieval.types import EmbeddingRecord, SearchResult


class VectorStore(abc.ABC):
    """Stores and retrieves embedding records by vector similarity."""

    @abc.abstractmethod
    async def put(self, record: EmbeddingRecord) -> None:
        """Store or update an embedding record."""

    @abc.abstractmethod
    async def put_many(self, records: list[EmbeddingRecord]) -> None:
        """Store multiple embedding records in batch."""

    @abc.abstractmethod
    async def search(
        self,
        query_vector: list[float],
        *,
        limit: int = 10,
        entity_type: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Find the most similar records to a query vector."""

    @abc.abstractmethod
    async def get(self, record_id: str) -> EmbeddingRecord | None:
        """Retrieve a specific record by ID."""

    @abc.abstractmethod
    async def delete(self, record_id: str) -> None:
        """Delete a specific record."""

    @abc.abstractmethod
    async def delete_by_source(self, source_entity_id: str) -> None:
        """Delete all records linked to a source entity."""

    @abc.abstractmethod
    async def count(self) -> int:
        """Total number of records in the store."""

    @abc.abstractmethod
    async def stats(self) -> dict[str, int]:
        """Record counts grouped by source_entity_type."""


class Embedder(abc.ABC):
    """Turns text into vectors. Model-agnostic port."""

    @abc.abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns one vector per input text."""

    @abc.abstractmethod
    async def embed_one(self, text: str) -> list[float]:
        """Embed a single text. Convenience wrapper."""

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """The dimensionality of vectors this embedder produces."""
