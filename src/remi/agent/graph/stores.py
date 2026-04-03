"""Knowledge graph store ABCs — Ontology, KnowledgeGraph, MemoryStore, KnowledgeStore.

DTOs (Entity, Relationship, etc.) live in ``remi.agent.graph.types``.
"""

from __future__ import annotations

import abc
from typing import Any

from remi.agent.graph.types import (
    AggregateResult,
    Entity,
    GraphLink,
    GraphObject,
    KnowledgeProvenance,
    LinkTypeDef,
    MemoryEntry,
    ObjectTypeDef,
    Relationship,
    TimelineEvent,
)

# ---------------------------------------------------------------------------
# Ontology — the schema layer (TBox: what types exist)
# ---------------------------------------------------------------------------


class Ontology(abc.ABC):
    """The domain vocabulary: object types, link types, constraints.

    This is the structural TBox — what kinds of things exist and how
    they can relate. Small, stable, loaded at boot, extended by learning.
    """

    @abc.abstractmethod
    async def list_object_types(self) -> list[ObjectTypeDef]: ...

    @abc.abstractmethod
    async def get_object_type(self, name: str) -> ObjectTypeDef | None: ...

    @abc.abstractmethod
    async def define_object_type(self, type_def: ObjectTypeDef) -> None: ...

    @abc.abstractmethod
    async def list_link_types(self) -> list[LinkTypeDef]: ...

    @abc.abstractmethod
    async def define_link_type(self, link_def: LinkTypeDef) -> None: ...


# ---------------------------------------------------------------------------
# KnowledgeGraph — instance store with links, traversal, codification
# ---------------------------------------------------------------------------


class KnowledgeGraph(Ontology):
    """Entity and relationship store with traversal and codification.

    Extends Ontology with instance CRUD, link management, graph traversal,
    aggregation, timeline, and knowledge codification. This is the ABox
    layer — the actual facts and relationships.
    """

    @abc.abstractmethod
    async def get_object(self, type_name: str, object_id: str) -> GraphObject | None: ...

    @abc.abstractmethod
    async def search_objects(
        self,
        type_name: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 50,
    ) -> list[GraphObject]: ...

    @abc.abstractmethod
    async def put_object(
        self, type_name: str, object_id: str, properties: dict[str, Any]
    ) -> None: ...

    @abc.abstractmethod
    async def delete_object(self, type_name: str, object_id: str) -> bool: ...

    @abc.abstractmethod
    async def get_links(
        self,
        object_id: str,
        *,
        link_type: str | None = None,
        direction: str = "both",
    ) -> list[GraphLink]: ...

    @abc.abstractmethod
    async def put_link(
        self,
        source_id: str,
        link_type: str,
        target_id: str,
        *,
        properties: dict[str, Any] | None = None,
    ) -> None: ...

    @abc.abstractmethod
    async def traverse(
        self,
        start_id: str,
        link_types: list[str] | None = None,
        *,
        max_depth: int = 3,
    ) -> list[GraphObject]: ...

    @abc.abstractmethod
    async def aggregate(
        self,
        type_name: str,
        metric: str,
        field: str | None = None,
        *,
        filters: dict[str, Any] | None = None,
        group_by: str | None = None,
    ) -> AggregateResult: ...

    @abc.abstractmethod
    async def record_event(
        self,
        object_type: str,
        object_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None: ...

    @abc.abstractmethod
    async def get_timeline(
        self,
        object_type: str,
        object_id: str,
        *,
        event_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[TimelineEvent]: ...

    @abc.abstractmethod
    async def codify(
        self,
        knowledge_type: str,
        data: dict[str, Any],
        *,
        provenance: KnowledgeProvenance = KnowledgeProvenance.INFERRED,
    ) -> str:
        """Store a piece of operational knowledge. Returns the entity ID."""
        ...




# ---------------------------------------------------------------------------
# MemoryStore — key-value episodic memory (separate concern from graph)
# ---------------------------------------------------------------------------


class MemoryStore(abc.ABC):
    """Key-value memory store for agent episodic memory.

    Intentionally separate from KnowledgeStore — these map to different
    backends (e.g. Postgres JSONB vs Neo4j).
    """

    @abc.abstractmethod
    async def store(
        self, namespace: str, key: str, value: str, *, ttl: int | None = None
    ) -> None: ...

    @abc.abstractmethod
    async def recall(self, namespace: str, key: str) -> str | None: ...

    @abc.abstractmethod
    async def search(self, namespace: str, query: str, *, limit: int = 5) -> list[MemoryEntry]: ...

    @abc.abstractmethod
    async def list_keys(self, namespace: str) -> list[str]: ...


# ---------------------------------------------------------------------------
# KnowledgeStore — low-level entity/relationship persistence
# ---------------------------------------------------------------------------


class KnowledgeStore(abc.ABC):
    """Low-level entity and relationship graph persistence.

    This is the storage backend for the knowledge graph — entities,
    relationships, traversal, namespaces. Does not inherit MemoryStore;
    the two concerns target different backends.
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
    async def list_namespaces(self) -> list[str]: ...

    @abc.abstractmethod
    async def delete_entity(self, namespace: str, entity_id: str) -> bool: ...
