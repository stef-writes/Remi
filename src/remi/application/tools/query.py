"""Unified query tool — single tool, all read operations.

One tool schema covers all read operations across portfolio, operations,
and intelligence. The LLM picks the right operation; the dispatcher
routes it in-process with no API calls.

Operations
----------
Portfolio:    dashboard, managers, manager_review, properties, rent_roll, rankings
Operations:   delinquency, expiring_leases, vacancies, leases, maintenance
Intelligence: search, delinquency_trend, occupancy_trend, rent_trend,
              maintenance_trend, ontology_schema, entity_graph

group_by parameter
------------------
Several operations accept ``group_by`` to return a pre-aggregated rollup
instead of a flat tenant/unit list.  Supported combinations:

  delinquency + group_by="property"  → ``by_property`` list sorted by total_balance desc.
                                       Each row: property_id, property_name, manager_id,
                                       manager_name, tenant_count, total_balance,
                                       balance_0_30, balance_30_plus.
  delinquency + group_by="manager"   → ``by_manager`` list sorted by total_balance desc.
  expiring_leases + group_by="manager" → ``by_manager`` list sorted by count desc.
  vacancies + group_by="manager"     → ``by_manager`` list sorted by vacant_count desc.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from remi.agent.signals import DomainSchema
from remi.agent.types import ToolArg, ToolDefinition, ToolProvider, ToolRegistry
from remi.application.core.protocols import PropertyStore
from remi.application.intelligence.search import SearchService
from remi.application.intelligence.trends import TrendResolver
from remi.application.operations.delinquency import DelinquencyResolver
from remi.application.operations.leases import LeaseResolver
from remi.application.operations.maintenance import MaintenanceResolver
from remi.application.operations.vacancies import VacancyResolver
from remi.application.portfolio.dashboard import DashboardBuilder
from remi.application.portfolio.managers import ManagerResolver
from remi.application.portfolio.properties import PropertyResolver
from remi.application.portfolio.rent_roll import RentRollResolver

_log = structlog.get_logger(__name__)

_OPERATIONS = (
    "dashboard, managers, manager_review, properties, rent_roll, rankings, "
    "delinquency, expiring_leases, vacancies, leases, maintenance, "
    "search, delinquency_trend, occupancy_trend, rent_trend, maintenance_trend, "
    "ontology_schema, entity_graph, data_coverage, entity_detail"
)


class QueryToolProvider(ToolProvider):
    """Registers the single unified ``query`` tool for all read operations."""

    def __init__(
        self,
        *,
        manager_resolver: ManagerResolver,
        property_resolver: PropertyResolver,
        rent_roll_resolver: RentRollResolver,
        dashboard_builder: DashboardBuilder,
        lease_resolver: LeaseResolver,
        maintenance_resolver: MaintenanceResolver,
        delinquency_resolver: DelinquencyResolver,
        vacancy_resolver: VacancyResolver,
        search_service: SearchService,
        trend_resolver: TrendResolver,
        property_store: PropertyStore,
        domain_schema: DomainSchema | None = None,
    ) -> None:
        self._managers = manager_resolver
        self._properties = property_resolver
        self._rent_roll = rent_roll_resolver
        self._dashboard = dashboard_builder
        self._leases = lease_resolver
        self._maintenance = maintenance_resolver
        self._delinquency = delinquency_resolver
        self._vacancies = vacancy_resolver
        self._search = search_service
        self._trends = trend_resolver
        self._ps = property_store
        self._domain_schema = domain_schema

    def register(self, registry: ToolRegistry) -> None:
        dispatch = {
            # -- Portfolio
            "dashboard": self._dashboard_op,
            "managers": self._managers_op,
            "manager_review": self._manager_review_op,
            "properties": self._properties_op,
            "rent_roll": self._rent_roll_op,
            "rankings": self._rankings_op,
            # -- Operations
            "delinquency": self._delinquency_op,
            "expiring_leases": self._expiring_leases_op,
            "vacancies": self._vacancies_op,
            "leases": self._leases_op,
            "maintenance": self._maintenance_op,
            # -- Data quality
            "data_coverage": self._data_coverage_op,
            # -- Entity detail (360-degree view)
            "entity_detail": self._entity_detail_op,
            # -- Intelligence
            "search": self._search_op,
            "delinquency_trend": self._delinquency_trend_op,
            "occupancy_trend": self._occupancy_trend_op,
            "rent_trend": self._rent_trend_op,
            "maintenance_trend": self._maintenance_trend_op,
            "ontology_schema": self._ontology_schema_op,
            "entity_graph": self._entity_graph_op,
        }

        async def query(args: dict[str, Any]) -> Any:
            operation = args.get("operation", "")
            if not operation:
                return {"error": "operation is required", "available": _OPERATIONS}
            handler = dispatch.get(operation)
            if handler is None:
                return {"error": f"Unknown operation: {operation!r}", "available": _OPERATIONS}
            try:
                return await handler(args)
            except Exception as exc:
                _log.warning("query_error", operation=operation, exc_info=True)
                return {"error": f"{operation} failed: {exc}"}

        registry.register(
            "query",
            query,
            ToolDefinition(
                name="query",
                description=(
                    "In-process data access — portfolio, operations, and intelligence "
                    "read operations. All sub-10ms, no API calls. "
                    f"Operations: {_OPERATIONS}. "
                    "ontology_schema and entity_graph return pre-rendered markdown — "
                    "relay the result to the user verbatim without reformatting. "
                    "entity_detail requires entity_type (manager|property|tenant|lease|document) "
                    "and entity_id — returns a 360-degree view of that entity and all connections."
                ),
                args=[
                    ToolArg(
                        name="operation",
                        description=f"One of: {_OPERATIONS}",
                        required=True,
                    ),
                    ToolArg(
                        name="manager_id",
                        description=(
                            "Manager ID or name — both are accepted and resolved automatically. "
                            "Pass 'Jake Kraus', 'jake-kraus', or 'Jake' — all resolve to the same manager. "
                            "Never call 'search' first just to look up an ID."
                        ),
                    ),
                    ToolArg(
                        name="property_id",
                        description=(
                            "Scope to a property — required for rent_roll, "
                            "optional for leases, maintenance, and trends"
                        ),
                    ),
                    ToolArg(name="sort_by", description="Sort field for 'rankings' (default: delinquency_rate)"),
                    ToolArg(name="days", description="Lookahead window for expiring_leases (default: 90)"),
                    ToolArg(name="status", description="Status filter for 'leases'"),
                    ToolArg(
                        name="group_by",
                        description=(
                            "Aggregate by dimension. "
                            "'property' with delinquency → per-property rollup sorted by total balance. "
                            "'manager' with delinquency, expiring_leases, or vacancies → per-manager rollup."
                        ),
                    ),
                    ToolArg(name="query", description="Search text (required for 'search')"),
                    ToolArg(name="periods", description="Number of periods for trend operations (default: 12)"),
                    ToolArg(
                        name="entity_type",
                        description=(
                            "Entity type for 'entity_detail' — one of: "
                            "manager, property, tenant, lease, document"
                        ),
                    ),
                    ToolArg(name="entity_id", description="Entity ID for 'entity_detail'"),
                    ToolArg(
                        name="fields",
                        description=(
                            "Comma-separated sub-entities to include in 'entity_detail' response. "
                            "Omit to get everything. Examples: 'leases,tenants' or 'leases,notes,documents'. "
                            "Tokens saved by requesting only what you need."
                        ),
                    ),
                ],
            ),
        )

    # -- Name resolution -----------------------------------------------------------

    async def _resolve_manager_id(self, raw: str) -> str | None:
        """Resolve a manager name or slug to a canonical manager_id.

        Accepts slugs ('jake-kraus'), display names ('Jake Kraus'), or partial
        names ('Jake'). Tries exact slug → exact name → token overlap, in order.
        Returns None if no manager matches.
        """
        if not raw:
            return None
        managers = await self._ps.list_managers()
        normalized = raw.lower().replace(" ", "-")
        raw_lower = raw.lower()
        # 1. Exact slug match
        for m in managers:
            if m.id == raw or m.id == normalized:
                return m.id
        # 2. Exact display-name match
        for m in managers:
            if m.name and m.name.lower() == raw_lower:
                return m.id
        # 3. Token overlap — "Jake" matches "Jake Kraus"
        tokens = set(raw_lower.split())
        best: str | None = None
        best_overlap = 0
        for m in managers:
            if m.name:
                name_tokens = set(m.name.lower().split())
                overlap = len(tokens & name_tokens)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best = m.id
        return best if best_overlap > 0 else None

    # -- Portfolio handlers --------------------------------------------------------

    async def _dashboard_op(self, args: dict[str, Any]) -> dict[str, Any]:
        overview = await self._dashboard.dashboard_overview(manager_id=args.get("manager_id"))
        return overview.model_dump(mode="json")

    async def _managers_op(self, args: dict[str, Any]) -> dict[str, Any]:
        summaries = await self._managers.list_manager_summaries()
        return {"managers": [s.model_dump(mode="json") for s in summaries]}

    async def _manager_review_op(self, args: dict[str, Any]) -> dict[str, Any]:
        raw = args.get("manager_id")
        if not raw:
            return {"error": "manager_id is required for manager_review"}
        mid = await self._resolve_manager_id(raw)
        if not mid:
            return {"error": f"Manager '{raw}' not found"}
        summary = await self._managers.aggregate_manager(mid)
        if not summary:
            return {"error": f"Manager '{raw}' not found"}
        result: dict[str, Any] = {"summary": summary.model_dump(mode="json")}
        action_items, notes = await asyncio.gather(
            self._ps.list_action_items(manager_id=mid),
            self._ps.list_notes(entity_type="PropertyManager", entity_id=mid),
        )
        if action_items:
            result["action_items"] = [ai.model_dump(mode="json") for ai in action_items]
        if notes:
            result["notes"] = [n.model_dump(mode="json") for n in notes]
        return result

    async def _properties_op(self, args: dict[str, Any]) -> dict[str, Any]:
        raw = args.get("manager_id")
        mid = await self._resolve_manager_id(raw) if raw else None
        items = await self._properties.list_properties(manager_id=mid)
        return {"properties": [p.model_dump(mode="json") for p in items]}

    async def _rent_roll_op(self, args: dict[str, Any]) -> dict[str, Any]:
        pid = args.get("property_id")
        if not pid:
            return {"error": "property_id is required for rent_roll"}
        result = await self._rent_roll.build_rent_roll(pid)
        if not result:
            return {"error": f"Property '{pid}' not found"}
        return result.model_dump(mode="json")

    async def _rankings_op(self, args: dict[str, Any]) -> dict[str, Any]:
        rows = await self._managers.rank_managers(sort_by=args.get("sort_by", "delinquency_rate"))
        return {"rankings": [r.model_dump(mode="json") for r in rows]}



    # -- Operations handlers -------------------------------------------------------

    async def _delinquency_op(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return delinquent tenants, optionally aggregated.

        group_by="property" → ranked ``by_property`` rollup (best for identifying
            problem properties — use this as the first call for property analysis).
        group_by="manager"  → ranked ``by_manager`` rollup.
        (omit)              → flat ``tenants`` list sorted by balance desc.
        """
        raw = args.get("manager_id")
        mid = await self._resolve_manager_id(raw) if raw else None
        board = await self._delinquency.delinquency_board(manager_id=mid)
        group_by = args.get("group_by")
        if group_by == "property":
            return _group_delinquency_by_property(board)
        if group_by == "manager":
            return _group_delinquency_by_manager(board)
        return board.model_dump(mode="json")

    async def _expiring_leases_op(self, args: dict[str, Any]) -> dict[str, Any]:
        raw = args.get("manager_id")
        mid = await self._resolve_manager_id(raw) if raw else None
        days = int(args.get("days", 90))
        cal = await self._leases.expiring_leases(days=days, manager_id=mid)
        if args.get("group_by") == "manager":
            return _group_leases_by_manager(cal)
        return cal.model_dump(mode="json")

    async def _vacancies_op(self, args: dict[str, Any]) -> dict[str, Any]:
        raw = args.get("manager_id")
        mid = await self._resolve_manager_id(raw) if raw else None
        tracker = await self._vacancies.vacancy_tracker(manager_id=mid)
        if args.get("group_by") == "manager":
            return _group_vacancies_by_manager(tracker)
        return tracker.model_dump(mode="json")

    async def _leases_op(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self._leases.list_leases(
            property_id=args.get("property_id"),
            status=args.get("status"),
        )
        return result.model_dump(mode="json")

    async def _maintenance_op(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self._maintenance.list_maintenance(property_id=args.get("property_id"))
        return result.model_dump(mode="json")

    # -- Data quality handlers -----------------------------------------------------

    async def _data_coverage_op(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return data completeness for one manager or all managers.

        Use this before citing occupancy rates, revenue, or delinquency figures
        so you know how much to trust the numbers and what caveat to include.
        """
        raw = args.get("manager_id")
        mid = await self._resolve_manager_id(raw) if raw else None
        summaries = (
            [await self._managers.aggregate_manager(mid)]
            if mid
            else await self._managers.list_manager_summaries()
        )
        rows = []
        for s in summaries:
            if s is None:
                continue
            rows.append({
                "manager_id": s.manager_id,
                "manager_name": s.name,
                "confidence": s.data_coverage.confidence,
                "has_rent_roll": s.data_coverage.has_rent_roll,
                "has_lease_data": s.data_coverage.has_lease_data,
                "has_delinquency_data": s.data_coverage.has_delinquency_data,
                "has_maintenance_data": s.data_coverage.has_maintenance_data,
                "unit_record_coverage": s.data_coverage.unit_record_coverage,
                "units_with_physical_data": s.data_coverage.units_with_physical_data,
                "missing_report_types": s.data_coverage.missing_report_types,
                "caveat": s.data_coverage.caveat,
            })
        return {
            "coverage": rows,
            "summary": {
                "full": sum(1 for r in rows if r["confidence"] == "full"),
                "partial": sum(1 for r in rows if r["confidence"] == "partial"),
                "sparse": sum(1 for r in rows if r["confidence"] == "sparse"),
            },
        }

    # -- Intelligence handlers -----------------------------------------------------

    async def _search_op(self, args: dict[str, Any]) -> dict[str, Any]:
        q = args.get("query", "")
        if not q:
            return {"error": "query is required for search"}
        results = await self._search.search(q)
        return {"results": [r.model_dump(mode="json") for r in results]}

    async def _delinquency_trend_op(self, args: dict[str, Any]) -> dict[str, Any]:
        raw = args.get("manager_id")
        mid = await self._resolve_manager_id(raw) if raw else None
        result = await self._trends.delinquency_trend(
            manager_id=mid,
            property_id=args.get("property_id"),
            periods=int(args.get("periods", 12)),
        )
        return result.model_dump(mode="json")

    async def _occupancy_trend_op(self, args: dict[str, Any]) -> dict[str, Any]:
        raw = args.get("manager_id")
        mid = await self._resolve_manager_id(raw) if raw else None
        result = await self._trends.occupancy_trend(
            manager_id=mid,
            property_id=args.get("property_id"),
            periods=int(args.get("periods", 12)),
        )
        return result.model_dump(mode="json")

    async def _rent_trend_op(self, args: dict[str, Any]) -> dict[str, Any]:
        raw = args.get("manager_id")
        mid = await self._resolve_manager_id(raw) if raw else None
        result = await self._trends.rent_trend(
            manager_id=mid,
            property_id=args.get("property_id"),
            periods=int(args.get("periods", 12)),
        )
        return result.model_dump(mode="json")

    async def _maintenance_trend_op(self, args: dict[str, Any]) -> dict[str, Any]:
        raw = args.get("manager_id")
        mid = await self._resolve_manager_id(raw) if raw else None
        result = await self._trends.maintenance_trend(
            manager_id=mid,
            property_id=args.get("property_id"),
            periods=int(args.get("periods", 12)),
        )
        return result.model_dump(mode="json")

    async def _ontology_schema_op(self, args: dict[str, Any]) -> str:
        if self._domain_schema is None:
            return "Domain schema not available."
        schema = self._domain_schema
        lines: list[str] = []

        lines.append(f"**Entity Types ({len(schema.entity_types)}):** "
                     + ", ".join(et.name for et in schema.entity_types))

        lines.append(f"\n**Key fields:**")
        for et in schema.entity_types:
            fields = ", ".join(et.key_fields) if et.key_fields else "—"
            lines.append(f"- {et.name}: {fields}")

        lines.append(f"\n**Relationships ({len(schema.relationships)}):**")
        for rel in schema.relationships:
            lines.append(f"- {rel.source} —[{rel.name}]→ {rel.target}")

        if schema.processes:
            lines.append(f"\n**Business Processes ({len(schema.processes)}):** "
                         + ", ".join(proc.name for proc in schema.processes))

        return "\n".join(lines)

    async def _entity_detail_op(self, args: dict[str, Any]) -> dict[str, Any]:
        """360-degree view of a single entity and all its connections.

        Supported entity_type values: manager, property, tenant, lease, document.
        entity_id is required in all cases.
        Use fields to request only specific sub-entities (e.g. "leases,tenants").
        """
        entity_type = (args.get("entity_type") or "").lower().strip()
        entity_id = (args.get("entity_id") or "").strip()
        if not entity_type:
            return {"error": "entity_type is required for entity_detail (manager, property, tenant, lease, document)"}
        if not entity_id:
            return {"error": "entity_id is required for entity_detail"}

        raw_fields = args.get("fields") or ""
        fields: frozenset[str] | None = (
            frozenset(f.strip().lower() for f in raw_fields.split(",") if f.strip())
            if raw_fields
            else None
        )

        if entity_type == "manager":
            return await self._detail_manager(entity_id, fields=fields)
        if entity_type == "property":
            return await self._detail_property(entity_id, fields=fields)
        if entity_type == "tenant":
            return await self._detail_tenant(entity_id, fields=fields)
        if entity_type == "lease":
            return await self._detail_lease(entity_id, fields=fields)
        if entity_type == "document":
            return await self._detail_document(entity_id, fields=fields)
        return {"error": f"Unknown entity_type {entity_type!r}. Use: manager, property, tenant, lease, document"}

    async def _detail_manager(
        self, manager_id: str, *, fields: frozenset[str] | None = None
    ) -> dict[str, Any]:
        want = fields.__contains__ if fields else lambda _: True
        manager = await self._ps.get_manager(manager_id)
        if manager is None:
            return {"error": f"Manager '{manager_id}' not found"}
        result: dict[str, Any] = {
            "entity_type": "manager",
            "manager": manager.model_dump(mode="json"),
        }

        fetch_props = fields is None or want("properties")
        fetch_units = fields is None or want("units")
        fetch_leases = fields is None or want("leases")
        fetch_tenants = fields is None or want("tenants")
        fetch_maintenance = fields is None or want("maintenance_requests")
        fetch_documents = fields is None or want("documents")
        fetch_actions = fields is None or want("action_items")
        fetch_notes = fields is None or want("notes")

        coros: list[Any] = []
        keys: list[str] = []
        if fetch_props:
            coros.append(self._ps.list_properties(manager_id=manager_id)); keys.append("properties")
        if fetch_actions:
            coros.append(self._ps.list_action_items(manager_id=manager_id)); keys.append("action_items")
        if fetch_notes:
            coros.append(self._ps.list_notes(entity_type="PropertyManager", entity_id=manager_id)); keys.append("notes")
        if fetch_documents:
            coros.append(self._ps.list_documents(manager_id=manager_id)); keys.append("documents")
        if fetch_maintenance:
            coros.append(self._ps.list_maintenance_requests(manager_id=manager_id)); keys.append("maintenance_requests")

        gathered = await asyncio.gather(*coros)
        raw: dict[str, Any] = dict(zip(keys, gathered))

        properties = raw.get("properties", [])
        prop_ids = {p.id for p in properties}

        if fetch_units or fetch_leases or fetch_tenants:
            unit_coros = [self._ps.list_units(property_id=pid) for pid in prop_ids] if (fetch_units or fetch_tenants) else []
            lease_coros = [self._ps.list_leases(property_id=pid) for pid in prop_ids] if (fetch_leases or fetch_tenants) else []
            units_grps, leases_grps = await asyncio.gather(
                asyncio.gather(*unit_coros),
                asyncio.gather(*lease_coros),
            )
            flat_units = [u.model_dump(mode="json") for grp in units_grps for u in grp]
            flat_leases = [ls.model_dump(mode="json") for grp in leases_grps for ls in grp]

            if fetch_tenants:
                tenant_ids = {ls["tenant_id"] for ls in flat_leases if ls.get("tenant_id")}
                tenants = await asyncio.gather(*[self._ps.get_tenant(tid) for tid in tenant_ids])
                result["tenants"] = [t.model_dump(mode="json") for t in tenants if t is not None]
            if fetch_units:
                result["units"] = flat_units
            if fetch_leases:
                result["leases"] = flat_leases

        if fetch_props:
            result["properties"] = [p.model_dump(mode="json") for p in properties]
        if fetch_maintenance:
            result["maintenance_requests"] = [m.model_dump(mode="json") for m in raw.get("maintenance_requests", [])]
        if fetch_documents:
            result["documents"] = [d.model_dump(mode="json") for d in raw.get("documents", [])]
        if fetch_actions:
            result["action_items"] = [ai.model_dump(mode="json") for ai in raw.get("action_items", [])]
        if fetch_notes:
            result["notes"] = [n.model_dump(mode="json") for n in raw.get("notes", [])]
        return result

    async def _detail_property(
        self, property_id: str, *, fields: frozenset[str] | None = None
    ) -> dict[str, Any]:
        want = fields.__contains__ if fields else lambda _: True
        prop = await self._ps.get_property(property_id)
        if prop is None:
            return {"error": f"Property '{property_id}' not found"}

        coros: list[Any] = []
        keys: list[str] = []
        if fields is None or want("units"):
            coros.append(self._ps.list_units(property_id=property_id)); keys.append("units")
        if fields is None or want("leases") or want("tenants"):
            coros.append(self._ps.list_leases(property_id=property_id)); keys.append("leases")
        if fields is None or want("maintenance_requests"):
            coros.append(self._ps.list_maintenance_requests(property_id=property_id)); keys.append("maintenance_requests")
        if fields is None or want("documents"):
            coros.append(self._ps.list_documents(property_id=property_id)); keys.append("documents")
        if fields is None or want("action_items"):
            coros.append(self._ps.list_action_items(property_id=property_id)); keys.append("action_items")
        if fields is None or want("notes"):
            coros.append(self._ps.list_notes(entity_type="Property", entity_id=property_id)); keys.append("notes")

        gathered = await asyncio.gather(*coros)
        raw: dict[str, Any] = dict(zip(keys, gathered))
        leases = raw.get("leases", [])

        manager: Any = None
        if fields is None or want("manager"):
            manager = await self._ps.get_manager(prop.manager_id) if prop.manager_id else None

        tenants: list[Any] = []
        if fields is None or want("tenants"):
            tenant_ids = {ls.tenant_id for ls in leases if ls.tenant_id}
            tenants_raw = await asyncio.gather(*[self._ps.get_tenant(tid) for tid in tenant_ids])
            tenants = [t for t in tenants_raw if t is not None]

        result: dict[str, Any] = {
            "entity_type": "property",
            "property": prop.model_dump(mode="json"),
        }
        if fields is None or want("manager"):
            result["manager"] = manager.model_dump(mode="json") if manager else None
        if "units" in raw:
            result["units"] = [u.model_dump(mode="json") for u in raw["units"]]
        if "leases" in raw and (fields is None or want("leases")):
            result["leases"] = [ls.model_dump(mode="json") for ls in leases]
        if tenants or (fields is None or want("tenants")):
            result["tenants"] = [t.model_dump(mode="json") for t in tenants]
        if "maintenance_requests" in raw:
            result["maintenance_requests"] = [m.model_dump(mode="json") for m in raw["maintenance_requests"]]
        if "documents" in raw:
            result["documents"] = [d.model_dump(mode="json") for d in raw["documents"]]
        if "action_items" in raw:
            result["action_items"] = [ai.model_dump(mode="json") for ai in raw["action_items"]]
        if "notes" in raw:
            result["notes"] = [n.model_dump(mode="json") for n in raw["notes"]]
        return result

    async def _detail_tenant(
        self, tenant_id: str, *, fields: frozenset[str] | None = None
    ) -> dict[str, Any]:
        want = fields.__contains__ if fields else lambda _: True
        tenant = await self._ps.get_tenant(tenant_id)
        if tenant is None:
            return {"error": f"Tenant '{tenant_id}' not found"}

        coros: list[Any] = []
        keys: list[str] = []
        # Leases are always fetched — they're needed to derive properties/units/managers
        coros.append(self._ps.list_leases(tenant_id=tenant_id)); keys.append("leases")
        if fields is None or want("balance_history"):
            coros.append(self._ps.list_balance_observations(tenant_id=tenant_id)); keys.append("balance_history")
        if fields is None or want("action_items"):
            coros.append(self._ps.list_action_items(tenant_id=tenant_id)); keys.append("action_items")
        if fields is None or want("notes"):
            coros.append(self._ps.list_notes(entity_type="Tenant", entity_id=tenant_id)); keys.append("notes")

        gathered = await asyncio.gather(*coros)
        raw: dict[str, Any] = dict(zip(keys, gathered))
        leases = raw.get("leases", [])
        property_ids = {ls.property_id for ls in leases if ls.property_id}
        unit_ids = {ls.unit_id for ls in leases if ls.unit_id}

        fetch_props = fields is None or want("properties") or want("managers")
        fetch_units = fields is None or want("units") or want("maintenance_requests")

        properties_raw: list[Any] = []
        units_raw: list[Any] = []
        if fetch_props or fetch_units:
            prop_coros = [self._ps.get_property(pid) for pid in property_ids] if fetch_props else []
            unit_coros = [self._ps.get_unit(uid) for uid in unit_ids] if fetch_units else []
            props_results, units_results = await asyncio.gather(
                asyncio.gather(*prop_coros),
                asyncio.gather(*unit_coros),
            )
            properties_raw = [p for p in props_results if p is not None]
            units_raw = [u for u in units_results if u is not None]

        managers_raw: list[Any] = []
        if fields is None or want("managers"):
            manager_ids = {p.manager_id for p in properties_raw if p.manager_id}
            managers_results = await asyncio.gather(*[self._ps.get_manager(mid) for mid in manager_ids])
            managers_raw = [m for m in managers_results if m is not None]

        maintenance_requests: list[dict[str, Any]] = []
        if fields is None or want("maintenance_requests"):
            for uid in unit_ids:
                reqs = await self._ps.list_maintenance_requests(unit_id=uid)
                maintenance_requests.extend(r.model_dump(mode="json") for r in reqs)

        result: dict[str, Any] = {
            "entity_type": "tenant",
            "tenant": tenant.model_dump(mode="json"),
        }
        if fields is None or want("leases"):
            result["leases"] = [ls.model_dump(mode="json") for ls in leases]
        if fields is None or want("properties"):
            result["properties"] = [p.model_dump(mode="json") for p in properties_raw]
        if fields is None or want("units"):
            result["units"] = [u.model_dump(mode="json") for u in units_raw]
        if fields is None or want("managers"):
            result["managers"] = [m.model_dump(mode="json") for m in managers_raw]
        if fields is None or want("balance_history"):
            result["balance_history"] = [b.model_dump(mode="json") for b in raw.get("balance_history", [])]
        if maintenance_requests or (fields is None or want("maintenance_requests")):
            result["maintenance_requests"] = maintenance_requests
        if fields is None or want("action_items"):
            result["action_items"] = [ai.model_dump(mode="json") for ai in raw.get("action_items", [])]
        if fields is None or want("notes"):
            result["notes"] = [n.model_dump(mode="json") for n in raw.get("notes", [])]
        return result

    async def _detail_lease(
        self, lease_id: str, *, fields: frozenset[str] | None = None
    ) -> dict[str, Any]:
        want = fields.__contains__ if fields else lambda _: True
        lease = await self._ps.get_lease(lease_id)
        if lease is None:
            return {"error": f"Lease '{lease_id}' not found"}

        coros: list[Any] = []
        keys: list[str] = []
        if fields is None or want("tenant"):
            coros.append(self._ps.get_tenant(lease.tenant_id) if lease.tenant_id else asyncio.sleep(0))
            keys.append("tenant")
        if fields is None or want("unit"):
            coros.append(self._ps.get_unit(lease.unit_id) if lease.unit_id else asyncio.sleep(0))
            keys.append("unit")
        if fields is None or want("property") or want("manager"):
            coros.append(self._ps.get_property(lease.property_id) if lease.property_id else asyncio.sleep(0))
            keys.append("property")
        if fields is None or want("documents"):
            coros.append(self._ps.list_documents(lease_id=lease_id)); keys.append("documents")
        if fields is None or want("notes"):
            coros.append(self._ps.list_notes(entity_type="Lease", entity_id=lease_id)); keys.append("notes")
        if fields is None or want("balance_history"):
            coros.append(
                self._ps.list_balance_observations(tenant_id=lease.tenant_id)
                if lease.tenant_id else asyncio.sleep(0)
            )
            keys.append("balance_history")

        gathered = await asyncio.gather(*coros)
        raw: dict[str, Any] = dict(zip(keys, gathered))

        prop = raw.get("property") if hasattr(raw.get("property"), "model_dump") else None
        manager: Any = None
        if fields is None or want("manager"):
            manager = await self._ps.get_manager(prop.manager_id) if prop and prop.manager_id else None

        result: dict[str, Any] = {"entity_type": "lease", "lease": lease.model_dump(mode="json")}
        if fields is None or want("tenant"):
            t = raw.get("tenant")
            result["tenant"] = t.model_dump(mode="json") if t and hasattr(t, "model_dump") else None
        if fields is None or want("unit"):
            u = raw.get("unit")
            result["unit"] = u.model_dump(mode="json") if u and hasattr(u, "model_dump") else None
        if fields is None or want("property"):
            result["property"] = prop.model_dump(mode="json") if prop else None
        if fields is None or want("manager"):
            result["manager"] = manager.model_dump(mode="json") if manager else None
        if fields is None or want("documents"):
            result["documents"] = [d.model_dump(mode="json") for d in raw.get("documents", [])]
        if fields is None or want("balance_history"):
            bh = raw.get("balance_history", [])
            result["balance_history"] = [b.model_dump(mode="json") for b in bh] if isinstance(bh, list) else []
        if fields is None or want("notes"):
            result["notes"] = [n.model_dump(mode="json") for n in raw.get("notes", [])]
        return result

    async def _detail_document(
        self, doc_id: str, *, fields: frozenset[str] | None = None
    ) -> dict[str, Any]:
        want = fields.__contains__ if fields else lambda _: True
        doc = await self._ps.get_document(doc_id)
        if doc is None:
            return {"error": f"Document '{doc_id}' not found"}

        coros: list[Any] = []
        keys: list[str] = []
        if fields is None or want("property"):
            coros.append(self._ps.get_property(doc.property_id) if doc.property_id else asyncio.sleep(0))
            keys.append("property")
        if fields is None or want("manager"):
            coros.append(self._ps.get_manager(doc.manager_id) if doc.manager_id else asyncio.sleep(0))
            keys.append("manager")
        if fields is None or want("unit"):
            coros.append(self._ps.get_unit(doc.unit_id) if doc.unit_id else asyncio.sleep(0))
            keys.append("unit")
        if fields is None or want("lease"):
            coros.append(self._ps.get_lease(doc.lease_id) if doc.lease_id else asyncio.sleep(0))
            keys.append("lease")

        gathered = await asyncio.gather(*coros)
        raw: dict[str, Any] = dict(zip(keys, gathered))

        result: dict[str, Any] = {"entity_type": "document", "document": doc.model_dump(mode="json")}
        for key in ("property", "manager", "unit", "lease"):
            if fields is None or want(key):
                val = raw.get(key)
                result[key] = val.model_dump(mode="json") if val and hasattr(val, "model_dump") else None
        return result

    async def _entity_graph_op(self, args: dict[str, Any]) -> str:
        raw: str | None = args.get("manager_id")
        manager_id = await self._resolve_manager_id(raw) if raw else None
        (
            managers, owners, properties, units,
            leases, tenants, maint, documents,
        ) = await asyncio.gather(
            self._ps.list_managers(),
            self._ps.list_owners(),
            self._ps.list_properties(manager_id=manager_id),
            self._ps.list_units(),
            self._ps.list_leases(),
            self._ps.list_tenants(),
            self._ps.list_maintenance_requests(),
            self._ps.list_documents(),
        )
        prop_ids = {p.id for p in properties}
        if manager_id:
            units = [u for u in units if u.property_id in prop_ids]
            unit_ids = {u.id for u in units}
            leases = [
                ls for ls in leases
                if ls.property_id in prop_ids or ls.unit_id in unit_ids
            ]
            maint = [m for m in maint if m.property_id in prop_ids]
            tenant_ids = {ls.tenant_id for ls in leases}
            tenants = [t for t in tenants if t.id in tenant_ids]
        scope = f" (manager: {manager_id})" if manager_id else " (full portfolio)"
        lines: list[str] = [f"## Entity Graph{scope}\n"]
        lines.append(
            f"- PropertyManagers: {len(managers)}\n"
            f"- Owners: {len(owners)}\n"
            f"- Properties: {len(properties)}\n"
            f"- Units: {len(units)}\n"
            f"- Leases: {len(leases)}\n"
            f"- Tenants: {len(tenants)}\n"
            f"- MaintenanceRequests: {len(maint)}\n"
            f"- Documents: {len(documents)}"
        )
        lines.append(
            "\n## Relationships\n"
            "- Property —[MANAGED_BY]→ PropertyManager\n"
            "- Property —[OWNED_BY]→ Owner\n"
            "- Unit —[BELONGS_TO]→ Property\n"
            "- Lease —[COVERS]→ Unit\n"
            "- Lease —[SIGNED_BY]→ Tenant\n"
            "- MaintenanceRequest —[AFFECTS]→ Unit"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Group-by aggregators — deterministic in-process, no LLM
# ---------------------------------------------------------------------------


def _group_delinquency_by_property(board: Any) -> dict[str, Any]:
    """Aggregate a DelinquencyBoard into a per-property rollup.

    Returns ``by_property`` sorted by ``total_balance`` descending so the
    worst offenders appear first.  Each entry carries both aging buckets
    (0-30 days, 30+ days) and the owning manager for cross-filtering.
    """
    groups: dict[str, dict[str, Any]] = {}
    for t in board.tenants:
        pid = t.property_id or "unassigned"
        g = groups.setdefault(pid, {
            "property_id": pid,
            "property_name": t.property_name or pid,
            "manager_id": t.manager_id,
            "manager_name": t.manager_name,
            "tenant_count": 0,
            "total_balance": 0.0,
            "balance_0_30": 0.0,
            "balance_30_plus": 0.0,
        })
        g["tenant_count"] += 1
        g["total_balance"] += t.balance_owed
        g["balance_0_30"] += t.balance_0_30
        g["balance_30_plus"] += t.balance_30_plus
    return {
        "total_delinquent": board.total_delinquent,
        "total_balance": board.total_balance,
        "by_property": sorted(
            groups.values(), key=lambda g: g["total_balance"], reverse=True
        ),
    }


def _group_delinquency_by_manager(board: Any) -> dict[str, Any]:
    """Aggregate a DelinquencyBoard into a per-manager rollup.

    Returns ``by_manager`` sorted by ``total_balance`` descending.
    """
    groups: dict[str, dict[str, Any]] = {}
    for t in board.tenants:
        mid = t.manager_id or "unassigned"
        g = groups.setdefault(mid, {
            "manager_id": mid,
            "manager_name": t.manager_name or mid,
            "tenant_count": 0,
            "total_balance": 0.0,
            "balance_0_30": 0.0,
            "balance_30_plus": 0.0,
        })
        g["tenant_count"] += 1
        g["total_balance"] += t.balance_owed
        g["balance_0_30"] += t.balance_0_30
        g["balance_30_plus"] += t.balance_30_plus
    return {
        "total_delinquent": board.total_delinquent,
        "total_balance": board.total_balance,
        "by_manager": sorted(groups.values(), key=lambda g: g["total_balance"], reverse=True),
    }


def _group_leases_by_manager(cal: Any) -> dict[str, Any]:
    """Aggregate a LeaseCalendar into a per-manager rollup.

    Returns ``by_manager`` sorted by lease ``count`` descending.
    """
    groups: dict[str, dict[str, Any]] = {}
    for le in cal.leases:
        mid = le.manager_id or "unassigned"
        g = groups.setdefault(mid, {
            "manager_id": mid,
            "manager_name": le.manager_name or mid,
            "count": 0,
            "month_to_month": 0,
            "total_monthly_rent": 0.0,
        })
        g["count"] += 1
        if le.is_month_to_month:
            g["month_to_month"] += 1
        g["total_monthly_rent"] += le.monthly_rent
    return {
        "days_window": cal.days_window,
        "total_expiring": cal.total_expiring,
        "by_manager": sorted(groups.values(), key=lambda g: g["count"], reverse=True),
    }


def _group_vacancies_by_manager(tracker: Any) -> dict[str, Any]:
    """Aggregate a VacancyTracker into a per-manager rollup.

    Returns ``by_manager`` sorted by ``vacant_count`` descending.
    """
    groups: dict[str, dict[str, Any]] = {}
    for u in tracker.units:
        mid = getattr(u, "manager_id", None) or "unassigned"
        mname = getattr(u, "manager_name", None) or mid
        g = groups.setdefault(mid, {
            "manager_id": mid,
            "manager_name": mname,
            "vacant_count": 0,
            "total_market_rent_at_risk": 0.0,
        })
        g["vacant_count"] += 1
        g["total_market_rent_at_risk"] += u.market_rent
    return {
        "total_vacant": tracker.total_vacant,
        "total_market_rent_at_risk": tracker.total_market_rent_at_risk,
        "by_manager": sorted(groups.values(), key=lambda g: g["vacant_count"], reverse=True),
    }
