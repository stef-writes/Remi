"""Workflow tools — deterministic multi-step data gathering as single tool calls.

Provides: manager_review, delinquency_review, lease_risk_review,
          draft_action_plan, approve_action_plan.

Workflow tools compose existing resolvers (ManagerResolver,
DashboardResolver, PropertyStore) into pre-built data packages
the agent would otherwise need 5–15 tool calls to assemble.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import structlog

from remi.agent.types import ToolArg, ToolDefinition, ToolProvider, ToolRegistry
from remi.application.core.models import (
    ActionItem,
    ActionItemStatus,
    Priority,
)
from remi.application.core.protocols import PropertyStore
from remi.application.views.dashboard import DashboardResolver
from remi.application.views.managers import ManagerResolver
from remi.types.identity import manager_id as _manager_id

_log = structlog.get_logger(__name__)


class SubAgentInvoker(Protocol):
    """Minimal interface for calling a sub-agent by name."""

    async def ask(self, agent_name: str, question: str, *, mode: str) -> tuple[str | None, str]: ...


async def _resolve_manager_id(
    ps: PropertyStore,
    args: dict[str, Any],
) -> str | None:
    """Resolve manager_id from args, accepting either manager_id or manager_name.

    Resolution order:
      1. Explicit ``manager_id`` — used as-is.
      2. ``manager_name`` — converted to deterministic slug, verified against store.
         Falls back to substring match on all managers if slug miss.
    """
    mid = args.get("manager_id")
    if mid:
        return mid

    name = args.get("manager_name")
    if not name:
        return None

    slug = _manager_id(name)
    mgr = await ps.get_manager(slug)
    if mgr:
        return slug

    all_managers = await ps.list_managers()
    query_lower = name.lower().strip()
    for m in all_managers:
        if m.name.lower().strip() == query_lower:
            return m.id
    for m in all_managers:
        if query_lower in m.name.lower() or m.name.lower() in query_lower:
            return m.id

    _log.warning(
        "manager_resolution_failed",
        name=name,
        slug=slug,
        available=[m.name for m in all_managers],
    )
    return None


class WorkflowToolProvider(ToolProvider):
    def __init__(
        self,
        property_store: PropertyStore,
        manager_resolver: ManagerResolver,
        dashboard_resolver: DashboardResolver,
        *,
        sub_agent: SubAgentInvoker | None = None,
    ) -> None:
        self._ps = property_store
        self._mr = manager_resolver
        self._ds = dashboard_resolver
        self._sub_agent = sub_agent

    def register(self, registry: ToolRegistry) -> None:
        ps = self._ps
        mr = self._mr
        ds = self._ds

        async def manager_review(args: dict[str, Any]) -> Any:
            manager_id = await _resolve_manager_id(ps, args)
            if not manager_id:
                return {
                    "error": "Could not resolve manager. Provide manager_id or manager_name.",
                }
            summary = await mr.aggregate_manager(manager_id)
            if not summary:
                return {"error": f"Manager '{manager_id}' not found"}

            result: dict[str, Any] = {"summary": summary.model_dump(mode="json")}

            if summary.total_delinquent_balance > 0:
                board = await ds.delinquency_board(manager_id=manager_id)
                result["delinquency"] = board.model_dump(mode="json")

            if summary.metrics.expiring_leases_90d > 0:
                calendar = await ds.lease_expiration_calendar(days=90, manager_id=manager_id)
                result["lease_expirations"] = calendar.model_dump(mode="json")

            if summary.metrics.vacant > 0:
                vacancies = await ds.vacancy_tracker(manager_id=manager_id)
                result["vacancies"] = vacancies.model_dump(mode="json")

            action_items = await ps.list_action_items(manager_id=manager_id)
            if action_items:
                result["action_items"] = [ai.model_dump(mode="json") for ai in action_items]

            notes = await ps.list_notes(
                entity_type="PropertyManager", entity_id=manager_id
            )
            if notes:
                result["notes"] = [n.model_dump(mode="json") for n in notes]

            return result

        registry.register(
            "manager_review",
            manager_review,
            ToolDefinition(
                name="manager_review",
                description=(
                    "Complete review for a manager — returns summary, "
                    "property breakdown, delinquency, lease expirations, vacancies, "
                    "open action items, and notes in a single call. Use this before "
                    "answering any question about a manager's performance. "
                    "Accepts either manager_id or manager_name (name is resolved "
                    "automatically to an ID)."
                ),
                args=[
                    ToolArg(
                        name="manager_id",
                        description="Manager ID to review (or use manager_name instead)",
                    ),
                    ToolArg(
                        name="manager_name",
                        description="Manager name — resolved to ID automatically",
                    ),
                ],
            ),
        )

        async def delinquency_review(args: dict[str, Any]) -> Any:
            manager_id = await _resolve_manager_id(ps, args)
            board = await ds.delinquency_board(manager_id=manager_id)
            result: dict[str, Any] = board.model_dump(mode="json")

            notes_by_tenant: dict[str, list[dict[str, Any]]] = {}
            actions_by_tenant: dict[str, list[dict[str, Any]]] = {}
            for t in board.tenants:
                tid = t.tenant_id
                tenant_notes = await ps.list_notes(
                    entity_type="Tenant", entity_id=tid
                )
                if tenant_notes:
                    notes_by_tenant[tid] = [n.model_dump(mode="json") for n in tenant_notes]

                tenant_actions = await ps.list_action_items(tenant_id=tid)
                if tenant_actions:
                    actions_by_tenant[tid] = [ai.model_dump(mode="json") for ai in tenant_actions]

            if notes_by_tenant:
                result["notes_by_tenant"] = notes_by_tenant
            if actions_by_tenant:
                result["actions_by_tenant"] = actions_by_tenant

            return result

        registry.register(
            "delinquency_review",
            delinquency_review,
            ToolDefinition(
                name="delinquency_review",
                description=(
                    "Complete delinquency picture — delinquent tenants with balances, "
                    "report notes, user notes, and action items per tenant. Optionally "
                    "scoped to a manager. Accepts either manager_id or manager_name."
                ),
                args=[
                    ToolArg(
                        name="manager_id",
                        description="Filter to a specific manager (optional, or use manager_name)",
                    ),
                    ToolArg(
                        name="manager_name",
                        description="Manager name — resolved to ID automatically",
                    ),
                ],
            ),
        )

        async def lease_risk_review(args: dict[str, Any]) -> Any:
            manager_id = await _resolve_manager_id(ps, args)
            days = int(args.get("days", 90))

            calendar = await ds.lease_expiration_calendar(days=days, manager_id=manager_id)
            vacancies = await ds.vacancy_tracker(manager_id=manager_id)

            revenue_at_risk = (
                sum(le.monthly_rent for le in calendar.leases) + vacancies.total_market_rent_at_risk
            )

            return {
                "lease_expirations": calendar.model_dump(mode="json"),
                "vacancies": vacancies.model_dump(mode="json"),
                "estimated_monthly_revenue_at_risk": round(revenue_at_risk, 2),
            }

        registry.register(
            "lease_risk_review",
            lease_risk_review,
            ToolDefinition(
                name="lease_risk_review",
                description=(
                    "Lease expiration and vacancy risk analysis — expiring leases, "
                    "month-to-month leases, current vacancies, and estimated revenue "
                    "at risk. Optionally scoped to a manager. Accepts either "
                    "manager_id or manager_name."
                ),
                args=[
                    ToolArg(
                        name="manager_id",
                        description="Filter to a specific manager (optional, or use manager_name)",
                    ),
                    ToolArg(
                        name="manager_name",
                        description="Manager name — resolved to ID automatically",
                    ),
                    ToolArg(
                        name="days",
                        description="Lookahead window in days (default: 90)",
                        type="integer",
                    ),
                ],
            ),
        )

        if self._sub_agent is not None:
            _sa = self._sub_agent

            async def draft_action_plan(args: dict[str, Any]) -> Any:
                manager_id = await _resolve_manager_id(ps, args)
                if not manager_id:
                    return {
                        "error": "Could not resolve manager. Provide manager_id or manager_name.",
                    }
                focus = args.get("focus", "all")

                summary = await mr.aggregate_manager(manager_id)
                if not summary:
                    return {"error": f"Manager '{manager_id}' not found"}

                review_data: dict[str, Any] = {
                    "manager_id": manager_id,
                    "manager_name": summary.name,
                    "focus": focus,
                    "summary": summary.model_dump(mode="json"),
                }

                if focus in ("delinquency", "all") and summary.total_delinquent_balance > 0:
                    board = await ds.delinquency_board(manager_id=manager_id)
                    review_data["delinquency"] = board.model_dump(mode="json")

                if focus in ("leases", "all") and summary.metrics.expiring_leases_90d > 0:
                    cal = await ds.lease_expiration_calendar(days=90, manager_id=manager_id)
                    review_data["lease_expirations"] = cal.model_dump(mode="json")

                if focus in ("maintenance", "all") and summary.metrics.open_maintenance > 0:
                    review_data["maintenance"] = {
                        "open": summary.metrics.open_maintenance,
                        "emergency": summary.emergency_maintenance,
                    }

                if focus in ("vacancies", "all") and summary.metrics.vacant > 0:
                    vac = await ds.vacancy_tracker(manager_id=manager_id)
                    review_data["vacancies"] = vac.model_dump(mode="json")

                existing = await ps.list_action_items(
                    manager_id=manager_id, status=ActionItemStatus.OPEN
                )
                if existing:
                    review_data["existing_action_items"] = [
                        ai.model_dump(mode="json") for ai in existing
                    ]

                payload = json.dumps(review_data, default=str)
                answer, _run_id = await _sa.ask("action_planner", payload, mode="agent")
                if not answer:
                    return {"error": "Action planner returned no response"}

                try:
                    parsed = json.loads(answer) if isinstance(answer, str) else answer
                except (json.JSONDecodeError, TypeError):
                    parsed = {"raw_response": answer}

                return parsed

            registry.register(
                "draft_action_plan",
                draft_action_plan,
                ToolDefinition(
                    name="draft_action_plan",
                    description=(
                        "Analyze a manager's properties and propose action items. "
                        "Returns a plan for the director to review — does NOT write "
                        "anything. Present the proposed items to the director and "
                        "use approve_action_plan upon their approval."
                    ),
                    args=[
                        ToolArg(
                            name="manager_id",
                            description="Manager to analyze (or use manager_name)",
                        ),
                        ToolArg(
                            name="manager_name",
                            description="Manager name — resolved to ID automatically",
                        ),
                        ToolArg(
                            name="focus",
                            description=(
                                "Focus area: delinquency, leases, maintenance, "
                                "vacancies, or all (default: all)"
                            ),
                        ),
                    ],
                ),
            )

        async def approve_action_plan(args: dict[str, Any]) -> Any:
            actions = args["actions"]
            if not isinstance(actions, list):
                return {"error": "actions must be a list"}

            import uuid

            created: list[dict[str, str]] = []
            for action in actions:
                item_id = f"ai-{uuid.uuid4().hex[:12]}"
                from datetime import date

                due: date | None = None
                if raw_due := action.get("due_date"):
                    due = date.fromisoformat(str(raw_due))

                item = ActionItem(
                    id=item_id,
                    title=action["title"],
                    description=action.get("description", ""),
                    priority=Priority(action.get("priority", "medium")),
                    manager_id=action.get("manager_id"),
                    property_id=action.get("property_id"),
                    tenant_id=action.get("tenant_id"),
                    due_date=due,
                )
                await ps.upsert_action_item(item)
                created.append({"id": item.id, "title": item.title})

            return {"created": created, "count": len(created)}

        registry.register(
            "approve_action_plan",
            approve_action_plan,
            ToolDefinition(
                name="approve_action_plan",
                description=(
                    "Write approved action items to the system. Only call this "
                    "after the director has reviewed and approved a plan from "
                    "draft_action_plan. Pass the list of approved items."
                ),
                args=[
                    ToolArg(
                        name="actions",
                        description=(
                            "List of action items to create, each with: title, "
                            "description, priority, manager_id, property_id, "
                            "tenant_id, due_date"
                        ),
                        type="object",
                        required=True,
                    ),
                ],
            ),
        )

        async def portfolio_comparison(args: dict[str, Any]) -> Any:
            sort_by = args.get("sort_by", "occupancy_rate")
            limit = int(args.get("limit", 0)) or None
            ascending = str(args.get("ascending", "false")).lower() == "true"
            rankings = await mr.rank_managers(
                sort_by=sort_by, ascending=ascending, limit=limit
            )
            return {
                "manager_count": len(rankings),
                "sort_by": sort_by,
                "ascending": ascending,
                "managers": [r.model_dump(mode="json") for r in rankings],
            }

        registry.register(
            "portfolio_comparison",
            portfolio_comparison,
            ToolDefinition(
                name="portfolio_comparison",
                description=(
                    "Compare all managers side-by-side on any metric — occupancy, "
                    "delinquency, vacancy loss, maintenance, loss-to-lease. Returns "
                    "a sorted table of every manager with full metrics. Use this for "
                    "any cross-manager ranking or comparison question."
                ),
                args=[
                    ToolArg(
                        name="sort_by",
                        description=(
                            "Metric to sort by (default: occupancy_rate). Options: "
                            "occupancy_rate, delinquency_rate, total_delinquent_balance, "
                            "loss_to_lease, vacancy_loss, open_maintenance, "
                            "expiring_leases_90d, total_units, property_count"
                        ),
                    ),
                    ToolArg(
                        name="ascending",
                        description="Sort ascending (default: false = worst first)",
                    ),
                    ToolArg(
                        name="limit",
                        description="Return only top N managers (default: all)",
                    ),
                ],
            ),
        )

        async def portfolio_health(args: dict[str, Any]) -> Any:
            overview = await ds.dashboard_overview()
            delinquency = await ds.delinquency_board()
            vacancies = await ds.vacancy_tracker()
            lease_risk = await ds.lease_expiration_calendar(days=90)
            needs_mgr = await ds.needs_manager()

            rankings = await mr.rank_managers(sort_by="delinquency_rate", limit=5)

            red_flags: list[str] = []
            if overview.occupancy_rate < 0.90:
                red_flags.append(
                    f"Portfolio occupancy {overview.occupancy_rate:.1%} is below 90%"
                )
            if delinquency.total_delinquent > 0:
                red_flags.append(
                    f"{delinquency.total_delinquent} delinquent tenants "
                    f"owing ${delinquency.total_balance:,.0f}"
                )
            if vacancies.total_vacant > 0:
                red_flags.append(
                    f"{vacancies.total_vacant} vacant units — "
                    f"${vacancies.total_market_rent_at_risk:,.0f}/mo at risk"
                )
            if lease_risk.total_expiring > 0:
                rent_at_risk = sum(le.monthly_rent for le in lease_risk.leases)
                red_flags.append(
                    f"{lease_risk.total_expiring} leases expiring in 90 days — "
                    f"${rent_at_risk:,.0f}/mo revenue at risk"
                )
            if needs_mgr.total > 0:
                red_flags.append(
                    f"{needs_mgr.total} properties have no manager assigned"
                )

            return {
                "red_flags": red_flags,
                "overview": overview.model_dump(mode="json"),
                "delinquency_summary": {
                    "total_delinquent": delinquency.total_delinquent,
                    "total_balance": delinquency.total_balance,
                    "top_5": [t.model_dump(mode="json") for t in delinquency.tenants[:5]],
                },
                "vacancy_summary": {
                    "total_vacant": vacancies.total_vacant,
                    "total_notice": vacancies.total_notice,
                    "market_rent_at_risk": vacancies.total_market_rent_at_risk,
                    "avg_days_vacant": vacancies.avg_days_vacant,
                },
                "lease_risk_summary": {
                    "expiring_90d": lease_risk.total_expiring,
                    "month_to_month": lease_risk.month_to_month_count,
                },
                "worst_managers": [r.model_dump(mode="json") for r in rankings],
                "unassigned_properties": needs_mgr.total,
            }

        registry.register(
            "portfolio_health",
            portfolio_health,
            ToolDefinition(
                name="portfolio_health",
                description=(
                    "Complete portfolio health check in a single call — red flags, "
                    "occupancy, delinquency, vacancies, lease risk, worst-performing "
                    "managers, and unassigned properties. Use this when the user asks "
                    "about overall portfolio status, problems, or 'what needs attention'. "
                    "No parameters needed."
                ),
                args=[],
            ),
        )

        async def portfolio_trends(args: dict[str, Any]) -> Any:
            manager_id = await _resolve_manager_id(ps, args) if (
                args.get("manager_id") or args.get("manager_name")
            ) else None
            property_id = args.get("property_id")
            periods = int(args.get("periods", 12))

            result: dict[str, Any] = {}
            kw = dict(manager_id=manager_id, property_id=property_id, periods=periods)

            delq = await ds.delinquency_trend(**kw)
            result["delinquency"] = delq.model_dump(mode="json")

            occ = await ds.occupancy_trend(**kw)
            result["occupancy"] = occ.model_dump(mode="json")

            rent = await ds.rent_trend(**kw)
            result["rent"] = rent.model_dump(mode="json")

            return result

        registry.register(
            "portfolio_trends",
            portfolio_trends,
            ToolDefinition(
                name="portfolio_trends",
                description=(
                    "Time-series trends for a portfolio — delinquency, occupancy, "
                    "and rent over time, grouped by month. Use this to answer questions "
                    "about how a manager's or property's performance has changed. "
                    "Returns direction indicators (improving/worsening/stable) and "
                    "monthly data points suitable for charting or comparison."
                ),
                args=[
                    ToolArg(
                        name="manager_id",
                        description="Manager ID to scope trends (or use manager_name)",
                    ),
                    ToolArg(
                        name="manager_name",
                        description="Manager name — resolved to ID automatically",
                    ),
                    ToolArg(
                        name="property_id",
                        description="Property ID to scope trends to a single property",
                    ),
                    ToolArg(
                        name="periods",
                        description="Number of monthly periods to return (default 12)",
                    ),
                ],
            ),
        )
