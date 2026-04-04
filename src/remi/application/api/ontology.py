"""REST endpoints for the unified ontology layer.

Domain-agnostic — operates purely through the KnowledgeGraph port.
Maps 1:1 to the CLI ``remi onto`` subcommands.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from remi.agent.graph.adapters.bridge import BridgedKnowledgeGraph
from remi.agent.graph.types import ObjectTypeDef, PropertyDef
from remi.application.api.ontology_schemas import (
    AggregateRequest,
    AggregateResponse,
    CodifyRequest,
    CodifyResponse,
    DefineTypeRequest,
    DefineTypeResponse,
    ObjectResponse,
    RelatedResponse,
    SchemaListResponse,
    SchemaTypeResponse,
    SearchRequest,
    SearchResponse,
    TimelineResponse,
)
from remi.application.api.dependencies import get_knowledge_graph
from remi.types.errors import NotFoundError

router = APIRouter(prefix="/ontology", tags=["ontology"])


# -- search -------------------------------------------------------------------


@router.get("/search/{type_name}", response_model=SearchResponse)
async def search_objects(
    type_name: str,
    order_by: str | None = Query(None, description="Sort field (prefix with - for desc)"),
    limit: int = Query(50, ge=1, le=1000),
    store: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> SearchResponse:
    """Search objects of any type with optional field filters.

    Filters are passed as arbitrary query params beyond the declared ones.
    """
    results = await store.search_objects(
        type_name,
        order_by=order_by,
        limit=limit,
    )
    return SearchResponse(count=len(results), objects=results)


@router.post("/search/{type_name}", response_model=SearchResponse)
async def search_objects_post(
    type_name: str,
    body: SearchRequest,
    store: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> SearchResponse:
    """Search with filters in the request body (for complex filter objects)."""
    results = await store.search_objects(
        type_name,
        filters=body.filters,
        order_by=body.order_by,
        limit=body.limit,
    )
    return SearchResponse(count=len(results), objects=results)


# -- get ----------------------------------------------------------------------


@router.get("/objects/{type_name}/{object_id}", response_model=ObjectResponse)
async def get_object(
    type_name: str,
    object_id: str,
    store: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> ObjectResponse:
    """Get a single object by type and ID."""
    obj = await store.get_object(type_name, object_id)
    if obj is None:
        raise NotFoundError(type_name, object_id)
    return ObjectResponse(object=obj)


# -- related ------------------------------------------------------------------


@router.get(
    "/related/{object_id}",
    response_model=RelatedResponse,
)
async def get_related(
    object_id: str,
    link_type: str | None = Query(None, description="Filter by link type"),
    direction: str = Query("both", description="both|outgoing|incoming"),
    max_depth: int = Query(1, ge=1, le=10, description="Traversal depth"),
    store: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> RelatedResponse:
    """Find related objects via link traversal."""
    if max_depth > 1:
        link_types = [link_type] if link_type else None
        nodes = await store.traverse(
            object_id,
            link_types=link_types,
            max_depth=max_depth,
        )
        return RelatedResponse(
            object_id=object_id,
            count=len(nodes),
            nodes=nodes,
            depth=max_depth,
        )

    links = await store.get_links(
        object_id,
        link_type=link_type,
        direction=direction,
    )
    return RelatedResponse(
        object_id=object_id,
        count=len(links),
        links=links,
    )


# -- aggregate ----------------------------------------------------------------


@router.post("/aggregate/{type_name}", response_model=AggregateResponse)
async def aggregate(
    type_name: str,
    body: AggregateRequest,
    store: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> AggregateResponse:
    """Compute aggregate metrics (count, sum, avg, min, max) across objects."""
    result = await store.aggregate(
        type_name,
        body.metric,
        body.field,
        filters=body.filters,
        group_by=body.group_by,
    )
    return AggregateResponse(
        type_name=type_name,
        metric=body.metric,
        field=body.field,
        result=result,
    )


# -- timeline -----------------------------------------------------------------


@router.get(
    "/timeline/{type_name}/{object_id}",
    response_model=TimelineResponse,
)
async def get_timeline(
    type_name: str,
    object_id: str,
    limit: int = Query(50, ge=1, le=1000),
    store: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> TimelineResponse:
    """Show event history for an object."""
    events = await store.get_timeline(
        type_name,
        object_id,
        limit=limit,
    )
    return TimelineResponse(
        object_type=type_name,
        object_id=object_id,
        count=len(events),
        events=events,
    )


# -- schema -------------------------------------------------------------------


@router.get("/schema", response_model=SchemaListResponse)
async def list_schema(
    store: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> SchemaListResponse:
    """List all defined object types and link types."""
    types = await store.list_object_types()
    links = await store.list_link_types()
    return SchemaListResponse(
        types=[t.model_dump(mode="json") for t in types],
        link_types=[lt.model_dump(mode="json") for lt in links],
    )


@router.get("/schema/{type_name}", response_model=SchemaTypeResponse)
async def get_schema_type(
    type_name: str,
    store: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> SchemaTypeResponse:
    """Describe a specific object type and its related link types."""
    ot = await store.get_object_type(type_name)
    if ot is None:
        raise NotFoundError("Type", type_name)
    links = await store.list_link_types()
    related = [
        lt.model_dump(mode="json")
        for lt in links
        if lt.source_type in (type_name, "*") or lt.target_type in (type_name, "*")
    ]
    return SchemaTypeResponse(type=ot.model_dump(mode="json"), related_links=related)


# -- codify -------------------------------------------------------------------


@router.post("/codify", response_model=CodifyResponse)
async def codify(
    body: CodifyRequest,
    store: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> CodifyResponse:
    """Codify operational knowledge into the ontology."""
    entity_id = await store.codify(
        body.knowledge_type,
        body.data,
        provenance=body.provenance,
    )

    if body.source_id and body.target_id:
        link_type = "CAUSES" if body.knowledge_type == "causal_link" else "RELATED_TO"
        await store.put_link(
            body.source_id,
            link_type,
            body.target_id,
            properties={"knowledge_id": entity_id},
        )

    return CodifyResponse(entity_id=entity_id, knowledge_type=body.knowledge_type)


# -- define -------------------------------------------------------------------


@router.post("/define", response_model=DefineTypeResponse)
async def define_type(
    body: DefineTypeRequest,
    store: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> DefineTypeResponse:
    """Define a new object type in the ontology."""
    props = tuple(
        PropertyDef(
            name=p.name,
            data_type=p.data_type,
            required=p.required,
            description=p.description,
        )
        for p in body.properties
    )
    type_def = ObjectTypeDef(
        name=body.name,
        description=body.description,
        properties=props,
        provenance=body.provenance,
    )
    await store.define_object_type(type_def)
    return DefineTypeResponse(type=type_def.model_dump(mode="json"))
