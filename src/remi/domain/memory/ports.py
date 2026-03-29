"""MemoryStore port — persistent memory for agents across runs."""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel, frozen=True):
    namespace: str
    key: str
    value: Any
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Entity(BaseModel):
    """A typed entity in the knowledge graph."""

    entity_id: str
    entity_type: str
    namespace: str = "default"
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Relationship(BaseModel, frozen=True):
    """A typed, directed relationship between two entities."""

    source_id: str
    target_id: str
    relation_type: str
    namespace: str = "default"
    properties: dict[str, Any] = Field(default_factory=dict)
    weight: float = 1.0
    created_at: datetime | None = None


class MemoryStore(abc.ABC):
    """Key-value memory store for backward compatibility."""

    @abc.abstractmethod
    async def store(
        self, namespace: str, key: str, value: Any, *, ttl: int | None = None
    ) -> None: ...

    @abc.abstractmethod
    async def recall(self, namespace: str, key: str) -> Any | None: ...

    @abc.abstractmethod
    async def search(
        self, namespace: str, query: str, *, limit: int = 5
    ) -> list[MemoryEntry]: ...

    @abc.abstractmethod
    async def list_keys(self, namespace: str) -> list[str]: ...


class KnowledgeStore(MemoryStore):
    """Extended memory store with entity/relationship graph capabilities.

    Inherits all key-value operations from MemoryStore and adds structured
    entity management and relationship traversal.
    """

    @abc.abstractmethod
    async def put_entity(self, entity: Entity) -> None: ...

    @abc.abstractmethod
    async def get_entity(self, namespace: str, entity_id: str) -> Entity | None: ...

    @abc.abstractmethod
    async def find_entities(
        self,
        namespace: str,
        entity_type: str | None = None,
        query: str | None = None,
        *,
        limit: int = 20,
    ) -> list[Entity]: ...

    @abc.abstractmethod
    async def put_relationship(self, rel: Relationship) -> None: ...

    @abc.abstractmethod
    async def get_relationships(
        self,
        namespace: str,
        entity_id: str,
        *,
        relation_type: str | None = None,
        direction: str = "outgoing",
    ) -> list[Relationship]: ...

    @abc.abstractmethod
    async def traverse(
        self,
        namespace: str,
        start_id: str,
        relation_types: list[str] | None = None,
        *,
        max_depth: int = 3,
    ) -> list[Entity]: ...

    @abc.abstractmethod
    async def delete_entity(self, namespace: str, entity_id: str) -> bool: ...
