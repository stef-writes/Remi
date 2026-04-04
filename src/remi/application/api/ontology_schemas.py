"""Pydantic schemas for the ontology REST API.

Typed request/response models for every ontology endpoint. These are the
wire format — the API router serializes domain types into these, and the
RemoteKnowledgeGraph deserializes them back.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from remi.agent.graph.types import (
    AggregateResult,
    GraphLink,
    GraphObject,
    KnowledgeProvenance,
    TimelineEvent,
)

# -- Shared -------------------------------------------------------------------


class PropertyInput(BaseModel):
    name: str
    data_type: str = "string"
    required: bool = False
    description: str = ""


# -- Requests -----------------------------------------------------------------


class SearchRequest(BaseModel):
    filters: dict[str, Any] | None = None
    order_by: str | None = None
    limit: int = 50


class AggregateRequest(BaseModel):
    metric: str
    field: str | None = None
    filters: dict[str, Any] | None = None
    group_by: str | None = None


class CodifyRequest(BaseModel):
    knowledge_type: str
    data: dict[str, Any]
    provenance: KnowledgeProvenance = KnowledgeProvenance.INFERRED
    source_id: str | None = None
    target_id: str | None = None


class DefineTypeRequest(BaseModel):
    name: str
    description: str = ""
    properties: list[PropertyInput] = Field(default_factory=list)
    provenance: KnowledgeProvenance = KnowledgeProvenance.USER_STATED


# -- Responses ----------------------------------------------------------------


class SearchResponse(BaseModel):
    count: int
    objects: list[GraphObject]


class ObjectResponse(BaseModel):
    ok: bool = True
    object: GraphObject | None = None
    error: str | None = None


class RelatedResponse(BaseModel):
    object_id: str
    count: int
    links: list[GraphLink] = Field(default_factory=list)
    nodes: list[GraphObject] = Field(default_factory=list)
    depth: int = 1


class AggregateResponse(BaseModel):
    type_name: str
    metric: str
    field: str | None = None
    result: AggregateResult | None = None


class TimelineResponse(BaseModel):
    object_type: str
    object_id: str
    count: int
    events: list[TimelineEvent]


class SchemaTypeResponse(BaseModel):
    type: dict[str, Any]
    related_links: list[dict[str, Any]] = Field(default_factory=list)


class SchemaListResponse(BaseModel):
    types: list[dict[str, Any]]
    link_types: list[dict[str, Any]]


class CodifyResponse(BaseModel):
    ok: bool = True
    entity_id: str
    knowledge_type: str


class DefineTypeResponse(BaseModel):
    ok: bool = True
    type: dict[str, Any]
