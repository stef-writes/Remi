"""Ontology tools — in-process calls to OntologyStore and SignalStore.

Provides: onto_signals, onto_explain, onto_search, onto_get, onto_related,
onto_aggregate, onto_timeline, onto_schema, onto_codify_observation,
onto_codify_policy, onto_codify_causal_link, onto_define_type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from remi.domain.ontology.types import (
    KnowledgeProvenance,
    ObjectTypeDef,
    PropertyDef,
)
from remi.domain.tools.ports import ToolArg, ToolDefinition, ToolRegistry

if TYPE_CHECKING:
    from remi.domain.ontology.ports import OntologyStore
    from remi.domain.signals.ports import SignalStore


def register_ontology_tools(
    registry: ToolRegistry,
    *,
    ontology_store: OntologyStore,
    signal_store: SignalStore | None = None,
) -> None:
    store = ontology_store

    # -- onto_signals ----------------------------------------------------------

    if signal_store is not None:
        _ss = signal_store

        async def onto_signals(args: dict[str, Any]) -> Any:
            signals = await _ss.list_signals(
                manager_id=args.get("manager_id"),
                property_id=args.get("property_id"),
                severity=args.get("severity"),
                signal_type=args.get("signal_type"),
            )
            return [
                {
                    "signal_id": s.signal_id,
                    "signal_type": s.signal_type,
                    "severity": s.severity.value,
                    "entity_type": s.entity_type,
                    "entity_id": s.entity_id,
                    "entity_name": s.entity_name,
                    "description": s.description,
                    "detected_at": s.detected_at.isoformat(),
                }
                for s in signals
            ]

        registry.register(
            "onto_signals",
            onto_signals,
            ToolDefinition(
                name="onto_signals",
                description=(
                    "List active entailed signals across the portfolio. Signals are "
                    "pre-computed domain states (e.g. LeaseExpirationCliff, "
                    "DelinquencyConcentration, VacancyDuration). Start here to "
                    "understand what needs attention before querying raw data."
                ),
                args=[
                    ToolArg(name="manager_id", description="Filter signals for a specific property manager"),
                    ToolArg(name="property_id", description="Filter signals for a specific property"),
                    ToolArg(name="severity", description="Filter by severity: low, medium, high, critical"),
                    ToolArg(name="signal_type", description="Filter by signal type name"),
                ],
            ),
        )

        # -- onto_explain ----------------------------------------------------------

        async def onto_explain(args: dict[str, Any]) -> Any:
            signal = await _ss.get_signal(args["signal_id"])
            if not signal:
                return {"error": f"Signal '{args['signal_id']}' not found"}
            return {
                "signal_id": signal.signal_id,
                "signal_type": signal.signal_type,
                "severity": signal.severity.value,
                "entity_type": signal.entity_type,
                "entity_id": signal.entity_id,
                "entity_name": signal.entity_name,
                "description": signal.description,
                "detected_at": signal.detected_at.isoformat(),
                "provenance": signal.provenance,
                "evidence": signal.evidence,
            }

        registry.register(
            "onto_explain",
            onto_explain,
            ToolDefinition(
                name="onto_explain",
                description=(
                    "Get the full evidence chain behind a specific signal. Returns "
                    "the structured proof: counts, percentages, affected entity IDs, "
                    "and threshold values that caused the signal to fire."
                ),
                args=[
                    ToolArg(name="signal_id", description="Signal ID to explain", required=True),
                ],
            ),
        )

    # -- onto_search -----------------------------------------------------------

    async def onto_search(args: dict[str, Any]) -> Any:
        type_name = args["type_name"]
        return await store.search_objects(
            type_name,
            filters=args.get("filters"),
            order_by=args.get("order_by"),
            limit=int(args.get("limit", 50)),
        )

    registry.register(
        "onto_search",
        onto_search,
        ToolDefinition(
            name="onto_search",
            description=(
                "Search objects of any type in the ontology with field filters. "
                "Types: Property, Unit, Lease, Tenant, Portfolio, PropertyManager, "
                "MaintenanceRequest, or any discovered type."
            ),
            args=[
                ToolArg(name="type_name", description="Object type to search", required=True),
                ToolArg(name="filters", description='Field filters as JSON object, e.g. {"status": "vacant"}', type="object"),
                ToolArg(name="order_by", description="Sort field (prefix with - for desc)"),
                ToolArg(name="limit", description="Max results (default: 50)", type="integer"),
            ],
        ),
    )

    # -- onto_get --------------------------------------------------------------

    async def onto_get(args: dict[str, Any]) -> Any:
        result = await store.get_object(args["type_name"], args["object_id"])
        return result or {"error": "Not found"}

    registry.register(
        "onto_get",
        onto_get,
        ToolDefinition(
            name="onto_get",
            description="Get a single object by type and ID from the ontology.",
            args=[
                ToolArg(name="type_name", description="Object type", required=True),
                ToolArg(name="object_id", description="Object ID", required=True),
            ],
        ),
    )

    # -- onto_related ----------------------------------------------------------

    async def onto_related(args: dict[str, Any]) -> Any:
        object_id = args["object_id"]
        link_type = args.get("link_type")
        direction = args.get("direction", "both")
        max_depth = int(args.get("max_depth", 1))

        if max_depth <= 1:
            return await store.get_links(
                object_id, link_type=link_type, direction=direction,
            )
        link_types = [link_type] if link_type else None
        return await store.traverse(object_id, link_types, max_depth=max_depth)

    registry.register(
        "onto_related",
        onto_related,
        ToolDefinition(
            name="onto_related",
            description="Find objects related to a given object via link traversal in the ontology.",
            args=[
                ToolArg(name="object_id", description="Object ID to start from", required=True),
                ToolArg(name="link_type", description="Filter by link type (e.g. BELONGS_TO, FOLLOWS, CAUSES)"),
                ToolArg(name="direction", description="'outgoing', 'incoming', or 'both' (default: both)"),
                ToolArg(name="max_depth", description="Traversal depth (default: 1)", type="integer"),
            ],
        ),
    )

    # -- onto_aggregate --------------------------------------------------------

    async def onto_aggregate(args: dict[str, Any]) -> Any:
        return await store.aggregate(
            args["type_name"],
            args["metric"],
            field=args.get("field"),
            filters=args.get("filters"),
            group_by=args.get("group_by"),
        )

    registry.register(
        "onto_aggregate",
        onto_aggregate,
        ToolDefinition(
            name="onto_aggregate",
            description="Compute aggregate metrics (count, sum, avg, min, max) across objects in the ontology.",
            args=[
                ToolArg(name="type_name", description="Object type", required=True),
                ToolArg(name="metric", description="Metric: count, sum, avg, min, max", required=True),
                ToolArg(name="field", description="Field to aggregate on (required for sum/avg/min/max)"),
                ToolArg(name="filters", description="Field filters as JSON object", type="object"),
                ToolArg(name="group_by", description="Group results by field"),
            ],
        ),
    )

    # -- onto_timeline ---------------------------------------------------------

    async def onto_timeline(args: dict[str, Any]) -> Any:
        event_types = args.get("event_types")
        if isinstance(event_types, str):
            event_types = [event_types]
        return await store.get_timeline(
            args["type_name"],
            args["object_id"],
            event_types=event_types,
            limit=int(args.get("limit", 50)),
        )

    registry.register(
        "onto_timeline",
        onto_timeline,
        ToolDefinition(
            name="onto_timeline",
            description="Show event history for an object in the ontology.",
            args=[
                ToolArg(name="type_name", description="Object type", required=True),
                ToolArg(name="object_id", description="Object ID", required=True),
                ToolArg(name="event_types", description="Filter by event type(s)"),
                ToolArg(name="limit", description="Max events (default: 50)", type="integer"),
            ],
        ),
    )

    # -- onto_schema -----------------------------------------------------------

    async def onto_schema(args: dict[str, Any]) -> Any:
        type_name = args.get("type_name")
        if type_name:
            td = await store.get_object_type(type_name)
            if not td:
                return {"error": f"Unknown type: {type_name}"}
            links = [
                lt for lt in await store.list_link_types()
                if lt.source_type == type_name or lt.target_type == type_name
            ]
            return {
                "type": td.model_dump(mode="json"),
                "links": [lt.model_dump(mode="json") for lt in links],
            }
        types = await store.list_object_types()
        return {"types": [t.model_dump(mode="json") for t in types]}

    registry.register(
        "onto_schema",
        onto_schema,
        ToolDefinition(
            name="onto_schema",
            description="Describe an object type's properties and links, or list all types if no type_name given.",
            args=[
                ToolArg(name="type_name", description="Object type (omit to list all)"),
            ],
        ),
    )

    # -- onto_codify_observation -----------------------------------------------

    async def onto_codify_observation(args: dict[str, Any]) -> Any:
        data: dict[str, Any] = {"description": args["description"]}
        if evidence := args.get("evidence"):
            data["evidence"] = evidence
        if refs := args.get("entity_refs"):
            data["entity_refs"] = refs if isinstance(refs, list) else refs.split(",")
        entity_id = await store.codify(
            "observation", data, provenance=KnowledgeProvenance.INFERRED,
        )
        return {"id": entity_id, "stored": True}

    registry.register(
        "onto_codify_observation",
        onto_codify_observation,
        ToolDefinition(
            name="onto_codify_observation",
            description="Record a pattern or observation the agent noticed into the ontology knowledge graph.",
            args=[
                ToolArg(name="description", description="Description of the observation", required=True),
                ToolArg(name="evidence", description="Supporting evidence"),
                ToolArg(name="entity_refs", description="Comma-separated entity IDs this relates to"),
            ],
        ),
    )

    # -- onto_codify_policy ----------------------------------------------------

    async def onto_codify_policy(args: dict[str, Any]) -> Any:
        data: dict[str, Any] = {"description": args["description"]}
        if trigger := args.get("trigger"):
            data["trigger"] = trigger
        if reqs := args.get("requirements"):
            data["requirements"] = reqs
        entity_id = await store.codify(
            "policy", data, provenance=KnowledgeProvenance.USER_STATED,
        )
        return {"id": entity_id, "stored": True}

    registry.register(
        "onto_codify_policy",
        onto_codify_policy,
        ToolDefinition(
            name="onto_codify_policy",
            description="Record a business rule or policy into the ontology knowledge graph.",
            args=[
                ToolArg(name="description", description="Policy description", required=True),
                ToolArg(name="trigger", description="What triggers this policy"),
                ToolArg(name="requirements", description="Requirements for the policy"),
            ],
        ),
    )

    # -- onto_codify_causal_link -----------------------------------------------

    async def onto_codify_causal_link(args: dict[str, Any]) -> Any:
        source_id = args["source_id"]
        target_id = args["target_id"]
        props: dict[str, Any] = {}
        if desc := args.get("description"):
            props["description"] = desc
        if conf := args.get("confidence"):
            props["confidence"] = float(conf)
        await store.put_link(source_id, "CAUSES", target_id, properties=props)
        return {"stored": True, "source_id": source_id, "target_id": target_id}

    registry.register(
        "onto_codify_causal_link",
        onto_codify_causal_link,
        ToolDefinition(
            name="onto_codify_causal_link",
            description="Record a causal relationship between two entities in the ontology.",
            args=[
                ToolArg(name="source_id", description="Source entity ID", required=True),
                ToolArg(name="target_id", description="Target entity ID", required=True),
                ToolArg(name="description", description="Causal relationship description"),
                ToolArg(name="confidence", description="Confidence score 0.0-1.0", type="number"),
            ],
        ),
    )

    # -- onto_define_type ------------------------------------------------------

    async def onto_define_type(args: dict[str, Any]) -> Any:
        name = args["name"]
        prop_defs: list[PropertyDef] = []
        if (raw_props := args.get("properties")) and isinstance(raw_props, list):
            for p in raw_props:
                if isinstance(p, dict):
                    prop_defs.append(PropertyDef(
                        name=p.get("name", ""),
                        data_type=p.get("data_type", "string"),
                        description=p.get("description", ""),
                    ))
                elif isinstance(p, str) and ":" in p:
                    pname, ptype = p.split(":", 1)
                    prop_defs.append(PropertyDef(name=pname, data_type=ptype))

        type_def = ObjectTypeDef(
            name=name,
            description=args.get("description", ""),
            properties=tuple(prop_defs),
            provenance=KnowledgeProvenance.DATA_DERIVED,
        )
        await store.define_object_type(type_def)
        return {"defined": True, "type": name, "property_count": len(prop_defs)}

    registry.register(
        "onto_define_type",
        onto_define_type,
        ToolDefinition(
            name="onto_define_type",
            description="Define a new object type in the ontology to extend the schema for discovered data.",
            args=[
                ToolArg(name="name", description="New type name", required=True),
                ToolArg(name="description", description="Type description"),
                ToolArg(name="properties", description="Property definitions as JSON array", type="object"),
            ],
        ),
    )
