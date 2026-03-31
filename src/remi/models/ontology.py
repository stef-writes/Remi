"""Domain schema (Ontology) and knowledge graph (KnowledgeGraph) ports.

The Ontology defines the vocabulary — object types, link types, constraints.
The KnowledgeGraph stores instances, relationships, and supports traversal.
These were previously merged into a single OntologyStore ABC.
"""

from __future__ import annotations

import abc
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeProvenance(StrEnum):
    """Tracks how a piece of knowledge entered the system.

    Single canonical provenance enum — used by both KnowledgeGraph and Signal.
    ``Provenance`` in ``models.signals`` is an alias for this class.
    """

    CORE = "core"
    SEEDED = "seeded"
    DATA_DERIVED = "data_derived"
    USER_STATED = "user_stated"
    INFERRED = "inferred"
    LEARNED = "learned"


class PropertyDef(BaseModel, frozen=True):
    """A single property (field) within an object type definition."""

    name: str
    data_type: str = "string"
    required: bool = False
    description: str = ""
    enum_values: list[str] | None = None
    default: Any = None


class KnowledgeLink(BaseModel, frozen=True):
    """A concrete link instance in the knowledge graph."""

    source_id: str
    link_type: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)


# Backward compatibility
OntologyLink = KnowledgeLink


class LinkTypeDef(BaseModel, frozen=True):
    """Defines a typed, directed relationship between two object types."""

    name: str
    source_type: str
    target_type: str
    cardinality: str = "many_to_many"
    description: str = ""
    provenance: KnowledgeProvenance = KnowledgeProvenance.CORE


class ActionDef(BaseModel, frozen=True):
    """An action that can be performed on an object type."""

    name: str
    description: str = ""
    workflow: str | None = None


class ObjectTypeDef(BaseModel, frozen=True):
    """Defines a type in the domain schema — both code-defined entities and
    dynamically discovered types share this shape."""

    name: str
    plural_name: str | None = None
    description: str = ""
    properties: tuple[PropertyDef, ...] = ()
    actions: tuple[ActionDef, ...] = ()
    provenance: KnowledgeProvenance = KnowledgeProvenance.CORE
    parent_type: str | None = None

    def property_names(self) -> frozenset[str]:
        return frozenset(p.name for p in self.properties)

    def required_properties(self) -> tuple[PropertyDef, ...]:
        return tuple(p for p in self.properties if p.required)


# ---------------------------------------------------------------------------
# Ontology — the schema layer (TBox structure: what types exist)
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

    Implementations bridge domain-specific stores (e.g. PropertyStore)
    with a generic KnowledgeStore for non-core types.
    """

    # -- Objects --------------------------------------------------------------

    @abc.abstractmethod
    async def get_object(self, type_name: str, object_id: str) -> dict[str, Any] | None: ...

    @abc.abstractmethod
    async def search_objects(
        self,
        type_name: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...

    @abc.abstractmethod
    async def put_object(
        self, type_name: str, object_id: str, properties: dict[str, Any]
    ) -> None: ...

    # -- Links ----------------------------------------------------------------

    @abc.abstractmethod
    async def get_links(
        self,
        object_id: str,
        *,
        link_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]: ...

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
    ) -> list[dict[str, Any]]: ...

    # -- Aggregation ----------------------------------------------------------

    @abc.abstractmethod
    async def aggregate(
        self,
        type_name: str,
        metric: str,
        field: str | None = None,
        *,
        filters: dict[str, Any] | None = None,
        group_by: str | None = None,
    ) -> Any: ...

    # -- Timeline -------------------------------------------------------------

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
    ) -> list[dict[str, Any]]: ...

    # -- Knowledge codification -----------------------------------------------

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


# Backward compatibility — existing code that imports OntologyStore still works
OntologyStore = KnowledgeGraph
