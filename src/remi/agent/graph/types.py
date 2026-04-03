"""Knowledge graph DTOs — entities, relationships, schema definitions.

ABCs live in ``remi.agent.graph.stores``.  This module owns pure data
types only — no abstract base classes.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeProvenance(StrEnum):
    """Tracks how a piece of knowledge entered the system."""

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
# Low-level graph persistence DTOs
# ---------------------------------------------------------------------------


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


class MemoryEntry(BaseModel, frozen=True):
    namespace: str
    key: str
    value: str
    created_at: datetime | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Typed return models for KnowledgeGraph port methods
# ---------------------------------------------------------------------------


class GraphObject(BaseModel):
    """A single object returned from the knowledge graph."""

    id: str
    type_name: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphLink(BaseModel, frozen=True):
    """A single link returned from get_links / traversal."""

    source_id: str
    link_type: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)


class TimelineEvent(BaseModel, frozen=True):
    """A single event in an entity's timeline."""

    id: str
    event_type: str
    object_type: str
    object_id: str
    timestamp: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class AggregateResult(BaseModel):
    """Result of an aggregation query."""

    value: float | int | None = None
    groups: dict[str, float | int | None] = Field(default_factory=dict)
