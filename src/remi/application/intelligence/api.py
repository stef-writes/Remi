"""Intelligence REST routes — dashboard, search, ontology, knowledge, events."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from remi.application.portfolio.models import (
    AutoAssignResult,
    DashboardOverview,
    DelinquencyBoard,
    DelinquencyTrend,
    LeaseCalendar,
    MaintenanceTrend,
    NeedsManagerResult,
    OccupancyTrend,
    RentTrend,
    VacancyTracker,
)
from remi.application.portfolio.queries import property_ids_for_owner
from remi.application.portfolio.models import RentRollResult
from remi.application.dependencies import Ctr
from remi.types.errors import NotFoundError

from .models import (
    GraphEdge,
    GraphNode,
    ObjectResponse,
    OperationalEdge,
    OperationalGraphResponse,
    OperationalNode,
    RelatedResponse,
    SchemaListResponse,
    SchemaTypeResponse,
    SearchApiResponse,
    SearchRequest,
    SearchResponse,
    SnapshotResponse,
    SubgraphResponse,
)

router = APIRouter(tags=["intelligence"])


# ---------------------------------------------------------------------------
# Dashboard routes
# ---------------------------------------------------------------------------

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@dashboard_router.get("/overview", response_model=DashboardOverview)
async def overview(c: Ctr, manager_id: str | None = None, owner_id: str | None = None) -> DashboardOverview:
    pids = await property_ids_for_owner(c.property_store, owner_id) if owner_id else None
    return await c.dashboard_resolver.dashboard_overview(manager_id=manager_id, property_ids=pids)


@dashboard_router.get("/delinquency", response_model=DelinquencyBoard)
async def delinquency(c: Ctr, manager_id: str | None = None, owner_id: str | None = None) -> DelinquencyBoard:
    pids = await property_ids_for_owner(c.property_store, owner_id) if owner_id else None
    return await c.dashboard_resolver.delinquency_board(manager_id=manager_id, property_ids=pids)


@dashboard_router.get("/leases/expiring", response_model=LeaseCalendar)
async def leases_expiring(c: Ctr, days: int = 90, manager_id: str | None = None, owner_id: str | None = None) -> LeaseCalendar:
    pids = await property_ids_for_owner(c.property_store, owner_id) if owner_id else None
    return await c.dashboard_resolver.lease_expiration_calendar(days=days, manager_id=manager_id, property_ids=pids)


@dashboard_router.get("/rent-roll/{property_id}", response_model=RentRollResult)
async def rent_roll(property_id: str, c: Ctr) -> RentRollResult:
    result = await c.rent_roll_resolver.build_rent_roll(property_id)
    if result is None:
        raise NotFoundError("Property", property_id)
    return result


@dashboard_router.get("/vacancies", response_model=VacancyTracker)
async def vacancies(c: Ctr, manager_id: str | None = None, owner_id: str | None = None) -> VacancyTracker:
    pids = await property_ids_for_owner(c.property_store, owner_id) if owner_id else None
    return await c.dashboard_resolver.vacancy_tracker(manager_id=manager_id, property_ids=pids)


@dashboard_router.get("/needs-manager", response_model=NeedsManagerResult)
async def needs_manager(c: Ctr) -> NeedsManagerResult:
    return await c.dashboard_resolver.needs_manager()


@dashboard_router.get("/trends/delinquency", response_model=DelinquencyTrend)
async def delinquency_trend(c: Ctr, manager_id: str | None = None, property_id: str | None = None, periods: int = 12) -> DelinquencyTrend:
    return await c.dashboard_resolver.delinquency_trend(manager_id=manager_id, property_id=property_id, periods=periods)


@dashboard_router.get("/trends/occupancy", response_model=OccupancyTrend)
async def occupancy_trend(c: Ctr, manager_id: str | None = None, property_id: str | None = None, periods: int = 12) -> OccupancyTrend:
    return await c.dashboard_resolver.occupancy_trend(manager_id=manager_id, property_id=property_id, periods=periods)


@dashboard_router.get("/trends/rent", response_model=RentTrend)
async def rent_trend(c: Ctr, manager_id: str | None = None, property_id: str | None = None, periods: int = 12) -> RentTrend:
    return await c.dashboard_resolver.rent_trend(manager_id=manager_id, property_id=property_id, periods=periods)


@dashboard_router.get("/trends/maintenance", response_model=MaintenanceTrend)
async def maintenance_trend(c: Ctr, manager_id: str | None = None, property_id: str | None = None, unit_id: str | None = None, periods: int = 12) -> MaintenanceTrend:
    return await c.dashboard_resolver.maintenance_trend(manager_id=manager_id, property_id=property_id, unit_id=unit_id, periods=periods)


@dashboard_router.post("/auto-assign", response_model=AutoAssignResult)
async def auto_assign(c: Ctr) -> AutoAssignResult:
    return await c.auto_assign_service.auto_assign()


# ---------------------------------------------------------------------------
# Search routes
# ---------------------------------------------------------------------------

search_router = APIRouter(prefix="/search", tags=["search"])


@search_router.get("", response_model=SearchApiResponse)
async def search(
    c: Ctr,
    q: str = Query(description="Search query"),
    types: str | None = Query(default=None, description="Comma-separated entity types"),
    manager_id: str | None = Query(default=None, description="Scope to manager"),
    limit: int = Query(default=10, ge=1, le=50),
) -> SearchApiResponse:
    type_list = [t.strip() for t in types.split(",") if t.strip()] if types else None
    results = await c.search_service.search(q, types=type_list, manager_id=manager_id, limit=limit)
    return SearchApiResponse(query=q, results=results, total=len(results))


# ---------------------------------------------------------------------------
# Knowledge routes
# ---------------------------------------------------------------------------

knowledge_router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class AssertFactRequest(BaseModel):
    entity_type: str
    entity_id: str | None = None
    properties: dict[str, str]
    related_to: str | None = None
    relation_type: str | None = None


class AddContextRequest(BaseModel):
    entity_type: str
    entity_id: str
    context: str


@knowledge_router.post("/assert")
async def assert_fact(body: AssertFactRequest, c: Ctr) -> dict[str, str]:
    from remi.application.tools.assertions import _assert_fact
    return await _assert_fact(
        c.property_store, c.event_store, c.event_bus,
        entity_type=body.entity_type, entity_id=body.entity_id,
        properties=body.properties, related_to=body.related_to, relation_type=body.relation_type,
    )


@knowledge_router.post("/context")
async def add_context(body: AddContextRequest, c: Ctr) -> dict[str, str]:
    from remi.application.tools.assertions import _add_context
    return await _add_context(
        c.property_store,
        entity_type=body.entity_type, entity_id=body.entity_id, context=body.context,
    )


# ---------------------------------------------------------------------------
# Events routes
# ---------------------------------------------------------------------------

events_router = APIRouter(prefix="/events", tags=["events"])


def _changeset_to_dict(cs: object) -> dict[str, Any]:
    from remi.application.core.events import ChangeSet
    assert isinstance(cs, ChangeSet)
    return {
        "id": cs.id, "source": cs.source.value, "source_detail": cs.source_detail,
        "adapter_name": cs.adapter_name, "report_type": cs.report_type,
        "document_id": cs.document_id, "timestamp": cs.timestamp.isoformat(),
        "summary": cs.summary(), "total_changes": cs.total_changes, "is_empty": cs.is_empty,
        "events": [
            {
                "entity_type": ev.entity_type, "entity_id": ev.entity_id,
                "change_type": ev.change_type.value, "source": ev.source.value,
                "timestamp": ev.timestamp.isoformat(),
                "fields": [{"field": fc.field, "old_value": fc.old_value, "new_value": fc.new_value} for fc in ev.fields],
            }
            for ev in cs.events
        ],
        "unchanged_ids": cs.unchanged_ids,
    }


@events_router.get("")
async def list_recent_events(c: Ctr, limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    changesets = await c.event_store.list_recent(limit=limit)
    return {"count": len(changesets), "changesets": [_changeset_to_dict(cs) for cs in changesets]}


@events_router.get("/{changeset_id}")
async def get_changeset(changeset_id: str, c: Ctr) -> dict[str, Any]:
    cs = await c.event_store.get(changeset_id)
    if cs is None:
        raise NotFoundError("ChangeSet", changeset_id)
    return _changeset_to_dict(cs)


@events_router.get("/entity/{entity_id}")
async def entity_history(entity_id: str, c: Ctr, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    changesets = await c.event_store.list_by_entity(entity_id, limit=limit)
    return {"entity_id": entity_id, "count": len(changesets), "changesets": [_changeset_to_dict(cs) for cs in changesets]}


# ---------------------------------------------------------------------------
# Ontology routes
# ---------------------------------------------------------------------------

ontology_router = APIRouter(prefix="/ontology", tags=["ontology"])


@ontology_router.get("/search/{type_name}", response_model=SearchResponse)
async def search_objects(type_name: str, c: Ctr, order_by: str | None = Query(None), limit: int = Query(50, ge=1, le=1000)) -> SearchResponse:
    results = await c.world_model.search_objects("", object_type=type_name, limit=limit)
    objects = [r.model_dump(mode="json") for r in results]
    return SearchResponse(count=len(objects), objects=objects)


@ontology_router.post("/search/{type_name}", response_model=SearchResponse)
async def search_objects_post(type_name: str, body: SearchRequest, c: Ctr) -> SearchResponse:
    results = await c.world_model.search_objects("", object_type=type_name, limit=body.limit)
    objects = [r.model_dump(mode="json") for r in results]
    return SearchResponse(count=len(objects), objects=objects)


@ontology_router.get("/objects/{type_name}/{object_id}", response_model=ObjectResponse)
async def get_object(type_name: str, object_id: str, c: Ctr) -> ObjectResponse:
    obj = await c.world_model.get_object(object_id)
    if obj is None:
        raise NotFoundError(type_name, object_id)
    return ObjectResponse(object=obj.model_dump(mode="json"))


@ontology_router.get("/related/{object_id}", response_model=RelatedResponse)
async def get_related(object_id: str, c: Ctr, link_type: str | None = Query(None), direction: str = Query("both"), max_depth: int = Query(1, ge=1, le=10)) -> RelatedResponse:
    links = await c.world_model.get_links(object_id, direction=direction, link_type=link_type)
    return RelatedResponse(object_id=object_id, count=len(links), links=[gl.model_dump(mode="json") for gl in links])


@ontology_router.get("/schema", response_model=SchemaListResponse)
async def list_schema(c: Ctr) -> SchemaListResponse:
    types = await c.world_model.schema()
    return SchemaListResponse(types=[t.model_dump(mode="json") for t in types], link_types=[])


@ontology_router.get("/schema/{type_name}", response_model=SchemaTypeResponse)
async def get_schema_type(type_name: str, c: Ctr) -> SchemaTypeResponse:
    all_types = await c.world_model.schema()
    ot = next((t for t in all_types if t.name == type_name), None)
    if ot is None:
        raise NotFoundError("Type", type_name)
    return SchemaTypeResponse(type=ot.model_dump(mode="json"), related_links=[])


def _label(obj: object, field: str = "name") -> str:
    val = getattr(obj, field, None)
    if val is None:
        val = getattr(obj, "id", "")
    if hasattr(val, "street"):
        return str(val.street)[:80]
    return str(val)[:80]


def _node(type_name: str, obj: object, label_field: str, display_fields: tuple[str, ...]) -> GraphNode:
    label = _label(obj, label_field)
    props = {}
    for f in display_fields:
        v = getattr(obj, f, None)
        if v is not None:
            props[f] = v.model_dump(mode="json") if hasattr(v, "model_dump") else v
    return GraphNode(id=getattr(obj, "id", ""), type_name=type_name, label=label, properties=props)


def _edge(source_id: str, link_type: str, target_id: str) -> GraphEdge | None:
    if source_id and target_id:
        return GraphEdge(source_id=source_id, target_id=target_id, link_type=link_type)
    return None


async def _build_snapshot(ps: Any, *, manager_id: str | None = None, owner_id: str | None = None) -> SnapshotResponse:
    from remi.application.core.protocols import PropertyStore as _PS
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    counts: dict[str, int] = {}
    edge_counts: dict[str, int] = {}
    node_ids: set[str] = set()

    def add(type_name: str, items: list[object], label_field: str, display: tuple[str, ...]) -> None:
        added = 0
        for obj in items:
            n = _node(type_name, obj, label_field, display)
            if n.id in node_ids:
                continue
            nodes.append(n)
            node_ids.add(n.id)
            added += 1
        counts[type_name] = added

    seen_edges: set[tuple[str, str, str]] = set()

    def link(src: str, lt: str, tgt: str) -> None:
        e = _edge(src, lt, tgt)
        if not e or e.source_id not in node_ids or e.target_id not in node_ids:
            return
        key = (e.source_id, e.link_type, e.target_id)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append(e)
        edge_counts[lt] = edge_counts.get(lt, 0) + 1

    managers = await ps.list_managers()
    owners = await ps.list_owners()
    properties = await ps.list_properties(manager_id=manager_id, owner_id=owner_id)
    prop_ids = {p.id for p in properties}
    units = await ps.list_units()
    leases = await ps.list_leases()
    tenants = await ps.list_tenants()
    vendors = await ps.list_vendors()
    maint = await ps.list_maintenance_requests()

    if manager_id or owner_id:
        units = [u for u in units if u.property_id in prop_ids]
    unit_ids = {u.id for u in units}
    if manager_id or owner_id:
        leases = [ls for ls in leases if ls.property_id in prop_ids or ls.unit_id in unit_ids]
        maint = [m for m in maint if m.property_id in prop_ids or m.unit_id in unit_ids]
    tenant_ids_in_scope = {ls.tenant_id for ls in leases}
    if manager_id or owner_id:
        tenants = [t for t in tenants if t.id in tenant_ids_in_scope]
    vendor_ids_in_scope = {m.vendor_id for m in maint if m.vendor_id}
    if manager_id or owner_id:
        vendors = [v for v in vendors if v.id in vendor_ids_in_scope]
        mgr_ids_in_scope = {p.manager_id for p in properties if p.manager_id}
        managers = [m for m in managers if m.id in mgr_ids_in_scope or m.id == manager_id]
        owner_ids_in_scope = {p.owner_id for p in properties if p.owner_id}
        owners = [o for o in owners if o.id in owner_ids_in_scope or o.id == owner_id]

    add("PropertyManager", managers, "name", ("name", "email", "company"))
    add("Owner", owners, "name", ("name", "email"))
    add("Property", properties, "name", ("name", "address", "property_type"))
    add("Unit", units, "unit_number", ("unit_number", "market_rent", "bedrooms", "sqft"))
    add("Lease", leases, "status", ("status", "monthly_rent", "start_date", "end_date"))
    add("Tenant", tenants, "name", ("name", "email", "status"))
    add("Vendor", vendors, "name", ("name", "category"))
    add("MaintenanceRequest", maint, "title", ("title", "priority", "status", "category"))

    documents = await ps.list_documents()
    if manager_id or owner_id:
        documents = [d for d in documents if (d.manager_id and d.manager_id in {m.id for m in managers}) or (d.property_id and d.property_id in prop_ids)]
    add("Document", documents, "filename", ("filename", "report_type", "kind", "row_count"))

    for p in properties:
        if p.manager_id:
            link(p.id, "MANAGED_BY", p.manager_id)
        if p.owner_id:
            link(p.id, "OWNED_BY", p.owner_id)
    for u in units:
        link(u.id, "BELONGS_TO", u.property_id)
    for ls in leases:
        link(ls.id, "COVERS", ls.unit_id)
        link(ls.id, "SIGNED_BY", ls.tenant_id)
    for m in maint:
        link(m.id, "AFFECTS", m.unit_id)
        if m.vendor_id:
            link(m.id, "SERVICED_BY", m.vendor_id)
    for d in documents:
        if d.property_id:
            link(d.id, "DOCUMENTS", d.property_id)
        if d.manager_id:
            link(d.id, "DOCUMENTS", d.manager_id)
    all_entities = list(managers) + list(owners) + list(properties) + list(units) + list(leases) + list(tenants) + list(vendors) + list(maint)
    for ent in all_entities:
        doc_id = getattr(ent, "source_document_id", None)
        if doc_id:
            link(ent.id, "EXTRACTED_FROM", doc_id)

    return SnapshotResponse(nodes=nodes, edges=edges, counts=counts, edge_counts=edge_counts, total_nodes=len(nodes), total_edges=len(edges))


@ontology_router.get("/snapshot", response_model=SnapshotResponse)
async def graph_snapshot(c: Ctr, manager_id: str | None = Query(None), owner_id: str | None = Query(None)) -> SnapshotResponse:
    return await _build_snapshot(c.property_store, manager_id=manager_id, owner_id=owner_id)


@ontology_router.get("/subgraph/{entity_id}", response_model=SubgraphResponse)
async def graph_subgraph(entity_id: str, c: Ctr, depth: int = Query(2, ge=1, le=4)) -> SubgraphResponse:
    full = await _build_snapshot(c.property_store)
    adj: dict[str, set[str]] = {}
    for e in full.edges:
        adj.setdefault(e.source_id, set()).add(e.target_id)
        adj.setdefault(e.target_id, set()).add(e.source_id)
    visited: set[str] = {entity_id}
    frontier = {entity_id}
    for _ in range(depth):
        next_frontier: set[str] = set()
        for nid in frontier:
            next_frontier |= adj.get(nid, set()) - visited
        visited |= next_frontier
        frontier = next_frontier
        if not frontier:
            break
    sub_nodes = [n for n in full.nodes if n.id in visited]
    sub_edges = [e for e in full.edges if e.source_id in visited and e.target_id in visited]
    return SubgraphResponse(center_id=entity_id, nodes=sub_nodes, edges=sub_edges)


def _build_operational_graph() -> OperationalGraphResponse:
    from remi.agent.signals import load_domain_yaml
    domain = load_domain_yaml()
    tbox = domain.get("tbox", {})
    abox = domain.get("abox", {})
    nodes: list[OperationalNode] = []
    edges_list: list[OperationalEdge] = []
    seen_ids: set[str] = set()
    processes: list[str] = []

    def add_node(node: OperationalNode) -> None:
        if node.id not in seen_ids:
            nodes.append(node)
            seen_ids.add(node.id)

    for process_name, process_data in tbox.items():
        if not isinstance(process_data, dict):
            continue
        processes.append(process_name)
        for sig in process_data.get("signals", []):
            sid = f"signal:{sig['name']}"
            add_node(OperationalNode(id=sid, kind="signal", label=sig["name"].replace("_", " "), process=process_name, properties={"severity": sig.get("severity", ""), "entity": sig.get("entity", ""), "description": sig.get("description", "")}))
        for pol in process_data.get("policies", []):
            pid = pol.get("id", f"policy:{process_name}:{pol.get('description', '')[:20]}")
            add_node(OperationalNode(id=pid, kind="policy", label=pol.get("description", pid)[:60], process=process_name, properties={"trigger": pol.get("trigger", ""), "deontic": pol.get("deontic", "")}))
        for chain in process_data.get("causal_chains", []):
            cause_id = f"cause:{process_name}:{chain['cause']}"
            effect_id = f"effect:{process_name}:{chain['effect']}"
            add_node(OperationalNode(id=cause_id, kind="cause", label=chain["cause"].replace("_", " "), process=process_name, properties={"description": chain.get("description", "")}))
            add_node(OperationalNode(id=effect_id, kind="effect", label=chain["effect"].replace("_", " "), process=process_name, properties={"description": chain.get("description", "")}))
            edges_list.append(OperationalEdge(source_id=cause_id, target_id=effect_id, link_type="CAUSES"))
    for wf in abox.get("workflows", []):
        wf_name = wf["name"]
        wf_id = f"workflow:{wf_name}"
        process = wf_name if wf_name in processes else "operations"
        add_node(OperationalNode(id=wf_id, kind="workflow", label=wf_name.replace("_", " ").title(), process=process))
        prev_id: str | None = None
        for step in wf.get("steps", []):
            step_id = step["id"]
            add_node(OperationalNode(id=step_id, kind="step", label=step.get("description", step_id)[:50], process=process))
            edges_list.append(OperationalEdge(source_id=wf_id, target_id=step_id, link_type="CONTAINS"))
            if prev_id:
                edges_list.append(OperationalEdge(source_id=prev_id, target_id=step_id, link_type="FOLLOWS"))
            prev_id = step_id

    return OperationalGraphResponse(nodes=nodes, edges=edges_list, processes=processes)


@ontology_router.get("/graph/operational", response_model=OperationalGraphResponse)
async def operational_graph() -> OperationalGraphResponse:
    return _build_operational_graph()
