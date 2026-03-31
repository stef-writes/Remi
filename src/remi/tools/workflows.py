"""Workflow tools — deterministic multi-step data gathering as single tool calls.

Provides: portfolio_review, delinquency_review, lease_risk_review,
          draft_action_plan, approve_action_plan.

Workflow tools compose existing services (ManagerReviewService,
DashboardQueryService, PropertyStore, KnowledgeGraph) into pre-built
data packages the agent would otherwise need 5–15 tool calls to assemble.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from remi.models.ontology import KnowledgeGraph
from remi.models.properties import (
    ActionItem,
    ActionItemPriority,
    ActionItemStatus,
    PropertyStore,
)
from remi.models.tools import ToolArg, ToolDefinition, ToolRegistry
from remi.services.dashboard import DashboardQueryService
from remi.services.manager_review import ManagerReviewService


class SubAgentInvoker(Protocol):
    """Minimal interface for calling a sub-agent by name."""

    async def ask(
        self, agent_name: str, question: str, *, mode: str
    ) -> tuple[str | None, str]: ...


def register_workflow_tools(
    registry: ToolRegistry,
    *,
    property_store: PropertyStore,
    knowledge_graph: KnowledgeGraph,
    manager_review: ManagerReviewService,
    dashboard_service: DashboardQueryService,
    sub_agent: SubAgentInvoker | None = None,
) -> None:
    ps = property_store
    kg = knowledge_graph
    mr = manager_review
    ds = dashboard_service

    # -- A1: portfolio_review --------------------------------------------------

    async def portfolio_review(args: dict[str, Any]) -> Any:
        manager_id = args["manager_id"]
        summary = await mr.aggregate_manager(manager_id)
        if not summary:
            return {"error": f"Manager '{manager_id}' not found"}

        result: dict[str, Any] = {"summary": summary.model_dump(mode="json")}

        if summary.total_delinquent_balance > 0:
            board = await ds.delinquency_board(manager_id=manager_id)
            result["delinquency"] = board.model_dump(mode="json")

        if summary.expiring_leases_90d > 0:
            calendar = await ds.lease_expiration_calendar(
                days=90, manager_id=manager_id
            )
            result["lease_expirations"] = calendar.model_dump(mode="json")

        if summary.vacant > 0:
            vacancies = await ds.vacancy_tracker(manager_id=manager_id)
            result["vacancies"] = vacancies.model_dump(mode="json")

        action_items = await ps.list_action_items(manager_id=manager_id)
        if action_items:
            result["action_items"] = [
                ai.model_dump(mode="json") for ai in action_items
            ]

        notes = await kg.search_objects(
            "Note",
            filters={"entity_type": "PropertyManager", "entity_id": manager_id},
            limit=50,
        )
        if notes:
            result["notes"] = notes

        return result

    registry.register(
        "portfolio_review",
        portfolio_review,
        ToolDefinition(
            name="portfolio_review",
            description=(
                "Complete portfolio review for a manager — returns summary, "
                "property breakdown, delinquency, lease expirations, vacancies, "
                "open action items, and notes in a single call. Use this before "
                "answering any question about a manager's performance."
            ),
            args=[
                ToolArg(
                    name="manager_id",
                    description="Manager ID to review",
                    required=True,
                ),
            ],
        ),
    )

    # -- A2: delinquency_review ------------------------------------------------

    async def delinquency_review(args: dict[str, Any]) -> Any:
        manager_id = args.get("manager_id")
        board = await ds.delinquency_board(manager_id=manager_id)
        result: dict[str, Any] = board.model_dump(mode="json")

        notes_by_tenant: dict[str, list[dict]] = {}
        actions_by_tenant: dict[str, list[dict]] = {}
        for t in board.tenants:
            tid = t.tenant_id
            tenant_notes = await kg.search_objects(
                "Note",
                filters={"entity_type": "Tenant", "entity_id": tid},
                limit=20,
            )
            if tenant_notes:
                notes_by_tenant[tid] = tenant_notes

            tenant_actions = await ps.list_action_items(tenant_id=tid)
            if tenant_actions:
                actions_by_tenant[tid] = [
                    ai.model_dump(mode="json") for ai in tenant_actions
                ]

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
                "scoped to a manager."
            ),
            args=[
                ToolArg(
                    name="manager_id",
                    description="Filter to a specific manager (optional)",
                ),
            ],
        ),
    )

    # -- A3: lease_risk_review -------------------------------------------------

    async def lease_risk_review(args: dict[str, Any]) -> Any:
        manager_id = args.get("manager_id")
        days = int(args.get("days", 90))

        calendar = await ds.lease_expiration_calendar(
            days=days, manager_id=manager_id
        )
        vacancies = await ds.vacancy_tracker(manager_id=manager_id)

        revenue_at_risk = sum(
            le.monthly_rent for le in calendar.leases
        ) + vacancies.total_market_rent_at_risk

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
                "at risk. Optionally scoped to a manager."
            ),
            args=[
                ToolArg(
                    name="manager_id",
                    description="Filter to a specific manager (optional)",
                ),
                ToolArg(
                    name="days",
                    description="Lookahead window in days (default: 90)",
                    type="integer",
                ),
            ],
        ),
    )

    # -- B1: draft_action_plan (agent-as-tool) ---------------------------------

    if sub_agent is not None:
        _sa = sub_agent

        async def draft_action_plan(args: dict[str, Any]) -> Any:
            manager_id = args["manager_id"]
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

            if focus in ("leases", "all") and summary.expiring_leases_90d > 0:
                cal = await ds.lease_expiration_calendar(
                    days=90, manager_id=manager_id
                )
                review_data["lease_expirations"] = cal.model_dump(mode="json")

            if focus in ("maintenance", "all") and summary.open_maintenance > 0:
                review_data["maintenance"] = {
                    "open": summary.open_maintenance,
                    "emergency": summary.emergency_maintenance,
                }

            if focus in ("vacancies", "all") and summary.vacant > 0:
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
            answer, _run_id = await _sa.ask(
                "action_planner", payload, mode="agent"
            )
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
                    "Analyze a manager's portfolio and propose action items. "
                    "Returns a plan for the director to review — does NOT write "
                    "anything. Present the proposed items to the director and "
                    "use approve_action_plan upon their approval."
                ),
                args=[
                    ToolArg(
                        name="manager_id",
                        description="Manager to analyze",
                        required=True,
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

    # -- B2: approve_action_plan (deterministic write) -------------------------

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
                priority=ActionItemPriority(action.get("priority", "medium")),
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
