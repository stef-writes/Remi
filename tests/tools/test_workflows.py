"""Tests for workflow tools — portfolio_review, delinquency_review, lease_risk_review."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from remi.knowledge.ontology_bridge import BridgedKnowledgeGraph
from remi.models.properties import (
    ActionItem,
    ActionItemPriority,
    Address,
    Lease,
    LeaseStatus,
    Portfolio,
    Property,
    PropertyManager,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
)
from remi.services.dashboard import DashboardQueryService
from remi.services.manager_review import ManagerReviewService
from remi.stores.memory import InMemoryKnowledgeStore
from remi.stores.properties import InMemoryPropertyStore
from remi.tools.registry import InMemoryToolRegistry
from remi.tools.workflows import register_workflow_tools

_ADDR = Address(street="100 Main St", city="Portland", state="OR", zip_code="97201")
TODAY = date.today()


@pytest.fixture
def setup():
    """Build stores, services, and register workflow tools. Returns (registry, ps, kg)."""
    ps = InMemoryPropertyStore()
    ks = InMemoryKnowledgeStore()
    kg = BridgedKnowledgeGraph(ks, core_types={
        "PropertyManager": (ps.get_manager, ps.list_managers),
        "Portfolio": (ps.get_portfolio, ps.list_portfolios),
        "Property": (ps.get_property, ps.list_properties),
        "Unit": (ps.get_unit, ps.list_units),
        "Lease": (ps.get_lease, ps.list_leases),
        "Tenant": (ps.get_tenant, ps.list_tenants),
        "ActionItem": (ps.get_action_item, ps.list_action_items),
    })

    mr = ManagerReviewService(property_store=ps)
    ds = DashboardQueryService(property_store=ps, knowledge_store=ks)

    registry = InMemoryToolRegistry()
    register_workflow_tools(
        registry,
        property_store=ps,
        knowledge_graph=kg,
        manager_review=mr,
        dashboard_service=ds,
    )

    return registry, ps, kg


async def _seed_portfolio(ps: InMemoryPropertyStore) -> None:
    """Seed manager → portfolio → property → units → leases → tenants."""
    await ps.upsert_manager(
        PropertyManager(id="mgr-1", name="Alice", email="a@test.com")
    )
    await ps.upsert_portfolio(
        Portfolio(id="pf-1", manager_id="mgr-1", name="Main Portfolio")
    )
    await ps.upsert_property(
        Property(id="prop-1", portfolio_id="pf-1", name="Oak Tower", address=_ADDR)
    )
    await ps.upsert_unit(
        Unit(
            id="u-1", property_id="prop-1", unit_number="101",
            status=UnitStatus.OCCUPIED,
            current_rent=Decimal("1200"), market_rent=Decimal("1300"),
        )
    )
    await ps.upsert_unit(
        Unit(
            id="u-2", property_id="prop-1", unit_number="102",
            status=UnitStatus.VACANT,
            current_rent=Decimal("0"), market_rent=Decimal("1400"),
        )
    )
    await ps.upsert_tenant(
        Tenant(
            id="t-1", name="Bob Tenant", status=TenantStatus.CURRENT,
            balance_owed=Decimal("500"), balance_0_30=Decimal("500"),
        )
    )
    await ps.upsert_lease(
        Lease(
            id="le-1", property_id="prop-1", unit_id="u-1", tenant_id="t-1",
            start_date=TODAY - timedelta(days=300),
            end_date=TODAY + timedelta(days=30),
            monthly_rent=Decimal("1200"), market_rent=Decimal("1300"),
            status=LeaseStatus.ACTIVE,
        )
    )


@pytest.mark.asyncio
async def test_portfolio_review_returns_summary(setup):
    registry, ps, kg = setup
    await _seed_portfolio(ps)

    fn, _ = registry.get("portfolio_review")
    result = await fn({"manager_id": "mgr-1"})

    assert "summary" in result
    assert result["summary"]["manager_id"] == "mgr-1"
    assert result["summary"]["total_units"] == 2
    assert result["summary"]["vacant"] == 1


@pytest.mark.asyncio
async def test_portfolio_review_includes_delinquency_when_present(setup):
    registry, ps, kg = setup
    await _seed_portfolio(ps)

    fn, _ = registry.get("portfolio_review")
    result = await fn({"manager_id": "mgr-1"})

    assert "delinquency" in result
    assert result["delinquency"]["total_delinquent"] == 1


@pytest.mark.asyncio
async def test_portfolio_review_includes_vacancies(setup):
    registry, ps, kg = setup
    await _seed_portfolio(ps)

    fn, _ = registry.get("portfolio_review")
    result = await fn({"manager_id": "mgr-1"})

    assert "vacancies" in result
    assert result["vacancies"]["total_vacant"] == 1


@pytest.mark.asyncio
async def test_portfolio_review_includes_lease_expirations(setup):
    registry, ps, kg = setup
    await _seed_portfolio(ps)

    fn, _ = registry.get("portfolio_review")
    result = await fn({"manager_id": "mgr-1"})

    assert "lease_expirations" in result
    assert result["lease_expirations"]["total_expiring"] >= 1


@pytest.mark.asyncio
async def test_portfolio_review_unknown_manager(setup):
    registry, ps, kg = setup

    fn, _ = registry.get("portfolio_review")
    result = await fn({"manager_id": "nonexistent"})

    assert "error" in result


@pytest.mark.asyncio
async def test_portfolio_review_includes_action_items(setup):
    registry, ps, kg = setup
    await _seed_portfolio(ps)

    item = ActionItem(
        id="ai-test", title="Follow up on rent",
        manager_id="mgr-1", priority=ActionItemPriority.HIGH,
    )
    await ps.upsert_action_item(item)

    fn, _ = registry.get("portfolio_review")
    result = await fn({"manager_id": "mgr-1"})

    assert "action_items" in result
    assert len(result["action_items"]) == 1
    assert result["action_items"][0]["title"] == "Follow up on rent"


@pytest.mark.asyncio
async def test_delinquency_review_returns_tenants(setup):
    registry, ps, kg = setup
    await _seed_portfolio(ps)

    fn, _ = registry.get("delinquency_review")
    result = await fn({})

    assert result["total_delinquent"] == 1
    assert result["tenants"][0]["tenant_id"] == "t-1"
    assert result["tenants"][0]["balance_owed"] == 500.0


@pytest.mark.asyncio
async def test_delinquency_review_scoped_to_manager(setup):
    registry, ps, kg = setup
    await _seed_portfolio(ps)

    fn, _ = registry.get("delinquency_review")
    result = await fn({"manager_id": "mgr-1"})

    assert result["total_delinquent"] == 1


@pytest.mark.asyncio
async def test_lease_risk_review_returns_data(setup):
    registry, ps, kg = setup
    await _seed_portfolio(ps)

    fn, _ = registry.get("lease_risk_review")
    result = await fn({"manager_id": "mgr-1"})

    assert "lease_expirations" in result
    assert "vacancies" in result
    assert "estimated_monthly_revenue_at_risk" in result
    assert result["estimated_monthly_revenue_at_risk"] > 0


@pytest.mark.asyncio
async def test_approve_action_plan_creates_items(setup):
    registry, ps, kg = setup
    await _seed_portfolio(ps)

    fn, _ = registry.get("approve_action_plan")
    result = await fn({
        "actions": [
            {
                "title": "Call tenant about late rent",
                "priority": "high",
                "manager_id": "mgr-1",
                "tenant_id": "t-1",
            },
            {
                "title": "List vacant unit",
                "priority": "medium",
                "manager_id": "mgr-1",
                "property_id": "prop-1",
            },
        ]
    })

    assert result["count"] == 2
    assert len(result["created"]) == 2

    items = await ps.list_action_items(manager_id="mgr-1")
    assert len(items) == 2


@pytest.mark.asyncio
async def test_workflow_tools_all_registered(setup):
    registry, ps, kg = setup

    expected = (
        "portfolio_review", "delinquency_review",
        "lease_risk_review", "approve_action_plan",
    )
    for name in expected:
        assert registry.has(name), f"Workflow tool '{name}' not registered"

    assert not registry.has("draft_action_plan"), (
        "draft_action_plan should only register when sub_agent is provided"
    )
