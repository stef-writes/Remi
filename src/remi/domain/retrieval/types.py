"""Retrieval domain types — embedding records and search results.

These are the Pydantic boundary types that flow between the vector
infrastructure and the rest of the system. Frozen models at all edges.
"""

from __future__ import annotations

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
