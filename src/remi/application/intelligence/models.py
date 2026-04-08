"""Intelligence read-model types — ontology schemas, search hits, graph visualization."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from remi.agent.graph import (
    AggregateResult,
    GraphLink,
    GraphObject,
    KnowledgeProvenance,
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


# -- Graph visualization -----------------------------------------------------


class GraphNode(BaseModel):
    """Lightweight node for graph visualization."""

    id: str
    type_name: str
    label: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """Edge for graph visualization."""

    source_id: str
    target_id: str
    link_type: str


class SnapshotResponse(BaseModel):
    """Full graph state for the live visualization."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    counts: dict[str, int] = Field(default_factory=dict)
    edge_counts: dict[str, int] = Field(default_factory=dict)
    total_nodes: int = 0
    total_edges: int = 0


class SubgraphResponse(BaseModel):
    """Ego-graph around a single entity."""

    center_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class OperationalNode(BaseModel):
    """Node in the operational intelligence graph."""

    id: str
    kind: str  # "step" | "cause" | "effect" | "policy" | "signal" | "workflow"
    label: str
    process: str  # business process: collections, leasing, maintenance, etc.
    properties: dict[str, Any] = Field(default_factory=dict)


class OperationalEdge(BaseModel):
    """Edge in the operational intelligence graph."""

    source_id: str
    target_id: str
    link_type: str  # FOLLOWS | CAUSES | TRIGGERS | MITIGATED_BY


class OperationalGraphResponse(BaseModel):
    """Operational knowledge from domain.yaml — workflows, causal chains, policies."""

    nodes: list[OperationalNode]
    edges: list[OperationalEdge]
    processes: list[str]


# -- Search models -----------------------------------------------------------


class SearchHit(BaseModel, frozen=True):
    entity_id: str
    entity_type: str
    label: str
    title: str
    subtitle: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchApiResponse(BaseModel, frozen=True):
    query: str
    results: list[SearchHit]
    total: int
