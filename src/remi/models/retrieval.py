"""Merged models module."""

from __future__ import annotations

import abc
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EmbeddingRecord(BaseModel, frozen=True):
    """A single embedded text chunk linked back to its source entity.

    The vector store holds these. Each record represents one
    semantically searchable surface for an entity — a tenant's notes,
    a maintenance description, a property address, etc.
    """

    id: str
    text: str
    vector: list[float]
    source_entity_id: str
    source_entity_type: str
    source_field: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class SearchResult(BaseModel, frozen=True):
    """A single result from a semantic search — record + similarity score."""

    record: EmbeddingRecord
    score: float

    @property
    def entity_id(self) -> str:
        return self.record.source_entity_id

    @property
    def entity_type(self) -> str:
        return self.record.source_entity_type

    @property
    def text(self) -> str:
        return self.record.text


class EmbeddingRequest(BaseModel, frozen=True):
    """A request to embed text for a specific entity field.

    Created by the pipeline, consumed by the embedder. Carries
    the metadata needed to construct an EmbeddingRecord once
    the vector is returned.
    """

    id: str
    text: str
    source_entity_id: str
    source_entity_type: str
    source_field: str
    metadata: dict[str, Any] = Field(default_factory=dict)


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

    async def metadata_text_search(
        self,
        query: str,
        *,
        fields: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Find records where metadata string values contain *query* (case-insensitive).

        If *fields* is given, only those metadata keys are checked.
        Default implementation returns an empty list; in-memory stores
        can override with a full scan.
        """
        return []


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
