"""Tests for the 6 previously-stubbed signal evaluators.

Covers: ConcentrationRisk, OccupancyDrift, OutlierPerformance,
PerformanceTrend, CommunicationGap, PolicyBreach.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from remi.knowledge.entailment.engine import EntailmentEngine
from remi.knowledge.ontology.bootstrap import load_domain_yaml
from remi.models.properties import (
    Address,
    Lease,
    LeaseStatus,
    MaintenanceRequest,
    MaintenanceStatus,
    Portfolio,
    Priority,
    Property,
    PropertyManager,
    Tenant,
    Unit,
    UnitStatus,
)
from remi.models.signals import DomainRulebook
from remi.services.snapshots import ManagerSnapshot, SnapshotService
from remi.stores.properties import InMemoryPropertyStore
from remi.stores.signals import InMemorySignalStore

_ADDR = Address(street="100 Main St", city="Portland", state="OR", zip_code="97201")


@pytest.fixture
def domain_rulebook() -> DomainRulebook:
    return DomainRulebook.from_yaml(load_domain_yaml())


@pytest.fixture
def signal_store() -> InMemorySignalStore:
    return InMemorySignalStore()


@pytest.fixture
def property_store() -> InMemoryPropertyStore:
    return InMemoryPropertyStore()


@pytest.fixture
def snapshot_service(property_store: InMemoryPropertyStore) -> SnapshotService:
    return SnapshotService(property_store=property_store)


@pytest.fixture
def engine(
    domain_rulebook: DomainRulebook,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
    snapshot_service: SnapshotService,
) -> EntailmentEngine:
    return EntailmentEngine(
        domain=domain_rulebook,
        property_store=property_store,
        signal_store=signal_store,
        snapshot_service=snapshot_service,
    )


@pytest.fixture
def engine_no_snapshots(
    domain_rulebook: DomainRulebook,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> EntailmentEngine:
    return EntailmentEngine(
        domain=domain_rulebook,
        property_store=property_store,
        signal_store=signal_store,
    )


async def _seed_two_managers(ps: InMemoryPropertyStore) -> dict[str, str]:
    """Seed two managers with portfolios and properties."""
    mgr1 = PropertyManager(id="mgr-1", name="Alice", email="a@test.com")
    mgr2 = PropertyManager(id="mgr-2", name="Bob", email="b@test.com")
    await ps.upsert_manager(mgr1)
    await ps.upsert_manager(mgr2)

    pf1 = Portfolio(id="pf-1", manager_id="mgr-1", name="Alice Portfolio")
    pf2 = Portfolio(id="pf-2", manager_id="mgr-2", name="Bob Portfolio")
    await ps.upsert_portfolio(pf1)
    await ps.upsert_portfolio(pf2)

    prop1 = Property(id="prop-1", portfolio_id="pf-1", name="Oak Tower", address=_ADDR)
    prop2 = Property(id="prop-2", portfolio_id="pf-1", name="Elm Court", address=_ADDR)
    prop3 = Property(id="prop-3", portfolio_id="pf-2", name="Pine Apts", address=_ADDR)
    await ps.upsert_property(prop1)
    await ps.upsert_property(prop2)
    await ps.upsert_property(prop3)

    return {
        "mgr1": "mgr-1", "mgr2": "mgr-2",
        "pf1": "pf-1", "pf2": "pf-2",
        "prop1": "prop-1", "prop2": "prop-2", "prop3": "prop-3",
    }


# =============================================================================
# ConcentrationRisk
# =============================================================================


@pytest.mark.asyncio
async def test_concentration_risk_fires_when_single_property_dominates(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> None:
    ids = await _seed_two_managers(property_store)

    for i in range(5):
        await property_store.upsert_unit(Unit(
            id=f"u-big-{i}", property_id=ids["prop1"], unit_number=f"A{i}",
            status=UnitStatus.OCCUPIED, current_rent=Decimal("2000"),
        ))
        await property_store.upsert_lease(Lease(
            id=f"l-big-{i}", unit_id=f"u-big-{i}", tenant_id=f"t-big-{i}",
            property_id=ids["prop1"],
            start_date=date.today() - timedelta(days=180),
            end_date=date.today() + timedelta(days=180),
            monthly_rent=Decimal("2000"), status=LeaseStatus.ACTIVE,
        ))

    await property_store.upsert_unit(Unit(
        id="u-small-0", property_id=ids["prop2"], unit_number="B0",
        status=UnitStatus.OCCUPIED, current_rent=Decimal("500"),
    ))
    await property_store.upsert_lease(Lease(
        id="l-small-0", unit_id="u-small-0", tenant_id="t-small-0",
        property_id=ids["prop2"],
        start_date=date.today() - timedelta(days=180),
        end_date=date.today() + timedelta(days=180),
        monthly_rent=Decimal("500"), status=LeaseStatus.ACTIVE,
    ))

    result = await engine.run_all()
    concentration_signals = [s for s in result.signals if s.signal_type == "ConcentrationRisk"]
    assert len(concentration_signals) >= 1
    sig = concentration_signals[0]
    assert sig.entity_id == "mgr-1"
    assert sig.evidence["concentrated_properties"][0]["property_name"] == "Oak Tower"
    assert sig.evidence["concentrated_properties"][0]["pct_of_total"] > 0.40


@pytest.mark.asyncio
async def test_concentration_risk_no_fire_when_balanced(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
) -> None:
    ids = await _seed_two_managers(property_store)

    prop_extra = Property(id="prop-extra", portfolio_id="pf-1", name="Maple Bldg", address=_ADDR)
    await property_store.upsert_property(prop_extra)

    for i, pid in enumerate([ids["prop1"], ids["prop2"], "prop-extra"]):
        await property_store.upsert_unit(Unit(
            id=f"u-eq-{i}", property_id=pid, unit_number=f"E{i}",
            status=UnitStatus.OCCUPIED, current_rent=Decimal("1000"),
        ))
        await property_store.upsert_lease(Lease(
            id=f"l-eq-{i}", unit_id=f"u-eq-{i}", tenant_id=f"t-eq-{i}",
            property_id=pid,
            start_date=date.today() - timedelta(days=180),
            end_date=date.today() + timedelta(days=180),
            monthly_rent=Decimal("1000"), status=LeaseStatus.ACTIVE,
        ))

    result = await engine.run_all()
    concentration_signals = [s for s in result.signals if s.signal_type == "ConcentrationRisk"]
    mgr1_signals = [s for s in concentration_signals if s.entity_id == "mgr-1"]
    assert len(mgr1_signals) == 0


# =============================================================================
# OccupancyDrift
# =============================================================================


@pytest.mark.asyncio
async def test_occupancy_drift_fires_on_declining_snapshots(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    snapshot_service: SnapshotService,
) -> None:
    await _seed_two_managers(property_store)

    now = datetime.now(UTC)
    for i, occ in enumerate([0.95, 0.90, 0.85]):
        snapshot_service._snapshots.append(ManagerSnapshot(
            manager_id="mgr-1", manager_name="Alice",
            timestamp=now - timedelta(days=30 * (2 - i)),
            occupancy_rate=occ, total_units=100, occupied=int(occ * 100),
            vacant=100 - int(occ * 100),
        ))

    result = await engine.run_all()
    drift_signals = [s for s in result.signals if s.signal_type == "OccupancyDrift"]
    assert len(drift_signals) >= 1
    assert drift_signals[0].entity_id == "mgr-1"
    assert drift_signals[0].evidence["declining_periods"] >= 2


@pytest.mark.asyncio
async def test_occupancy_drift_no_fire_without_snapshots(
    engine_no_snapshots: EntailmentEngine,
    property_store: InMemoryPropertyStore,
) -> None:
    await _seed_two_managers(property_store)
    result = await engine_no_snapshots.run_all()
    drift_signals = [s for s in result.signals if s.signal_type == "OccupancyDrift"]
    assert len(drift_signals) == 0


@pytest.mark.asyncio
async def test_occupancy_drift_no_fire_on_stable(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    snapshot_service: SnapshotService,
) -> None:
    await _seed_two_managers(property_store)

    now = datetime.now(UTC)
    for i in range(3):
        snapshot_service._snapshots.append(ManagerSnapshot(
            manager_id="mgr-1", manager_name="Alice",
            timestamp=now - timedelta(days=30 * (2 - i)),
            occupancy_rate=0.92, total_units=100, occupied=92, vacant=8,
        ))

    result = await engine.run_all()
    drift_signals = [s for s in result.signals if s.signal_type == "OccupancyDrift"]
    assert len(drift_signals) == 0


# =============================================================================
# OutlierPerformance
# =============================================================================


@pytest.mark.asyncio
async def test_outlier_performance_flags_bottom_quartile(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
) -> None:
    ids = await _seed_two_managers(property_store)

    for i in range(10):
        await property_store.upsert_unit(Unit(
            id=f"u-alice-{i}", property_id=ids["prop1"], unit_number=f"A{i}",
            status=UnitStatus.OCCUPIED, current_rent=Decimal("1000"),
        ))

    for i in range(10):
        status = UnitStatus.VACANT if i < 8 else UnitStatus.OCCUPIED
        await property_store.upsert_unit(Unit(
            id=f"u-bob-{i}", property_id=ids["prop3"], unit_number=f"B{i}",
            status=status, current_rent=Decimal("500") if status == UnitStatus.OCCUPIED else Decimal("0"),
        ))

    result = await engine.run_all()
    outlier_signals = [s for s in result.signals if s.signal_type == "OutlierPerformance"]
    assert len(outlier_signals) >= 1
    assert outlier_signals[0].entity_id == "mgr-2"


@pytest.mark.asyncio
async def test_outlier_performance_needs_multiple_managers(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
) -> None:
    mgr = PropertyManager(id="solo-mgr", name="Solo", email="s@test.com")
    await property_store.upsert_manager(mgr)
    pf = Portfolio(id="solo-pf", manager_id="solo-mgr", name="Solo PF")
    await property_store.upsert_portfolio(pf)
    prop = Property(id="solo-prop", portfolio_id="solo-pf", name="Solo Prop", address=_ADDR)
    await property_store.upsert_property(prop)

    result = await engine.run_all()
    outlier_signals = [s for s in result.signals if s.signal_type == "OutlierPerformance"]
    assert len(outlier_signals) == 0


# =============================================================================
# PerformanceTrend
# =============================================================================


@pytest.mark.asyncio
async def test_performance_trend_fires_on_improving(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    snapshot_service: SnapshotService,
) -> None:
    await _seed_two_managers(property_store)

    now = datetime.now(UTC)
    for i, occ in enumerate([0.80, 0.85, 0.92]):
        snapshot_service._snapshots.append(ManagerSnapshot(
            manager_id="mgr-1", manager_name="Alice",
            timestamp=now - timedelta(days=30 * (2 - i)),
            occupancy_rate=occ, total_units=100, occupied=int(occ * 100),
            vacant=100 - int(occ * 100),
            total_rent=float(occ * 100 * 1000),
        ))

    result = await engine.run_all()
    trend_signals = [s for s in result.signals if s.signal_type == "PerformanceTrend"]
    assert len(trend_signals) >= 1
    assert trend_signals[0].evidence["direction"] == "improving"


@pytest.mark.asyncio
async def test_performance_trend_fires_on_declining(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    snapshot_service: SnapshotService,
) -> None:
    await _seed_two_managers(property_store)

    now = datetime.now(UTC)
    for i, occ in enumerate([0.95, 0.88, 0.80]):
        snapshot_service._snapshots.append(ManagerSnapshot(
            manager_id="mgr-1", manager_name="Alice",
            timestamp=now - timedelta(days=30 * (2 - i)),
            occupancy_rate=occ, total_units=100, occupied=int(occ * 100),
            vacant=100 - int(occ * 100),
            total_rent=float(occ * 100 * 1000),
        ))

    result = await engine.run_all()
    trend_signals = [s for s in result.signals if s.signal_type == "PerformanceTrend"]
    assert len(trend_signals) >= 1
    assert trend_signals[0].evidence["direction"] == "declining"


@pytest.mark.asyncio
async def test_performance_trend_no_fire_on_mixed(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    snapshot_service: SnapshotService,
) -> None:
    await _seed_two_managers(property_store)

    now = datetime.now(UTC)
    for i, occ in enumerate([0.90, 0.85, 0.92]):
        snapshot_service._snapshots.append(ManagerSnapshot(
            manager_id="mgr-1", manager_name="Alice",
            timestamp=now - timedelta(days=30 * (2 - i)),
            occupancy_rate=occ, total_units=100, occupied=int(occ * 100),
            vacant=100 - int(occ * 100),
            total_rent=float(occ * 100 * 1000),
        ))

    result = await engine.run_all()
    trend_signals = [
        s for s in result.signals
        if s.signal_type == "PerformanceTrend" and s.entity_id == "mgr-1"
    ]
    assert len(trend_signals) == 0


# =============================================================================
# CommunicationGap
# =============================================================================


@pytest.mark.asyncio
async def test_communication_gap_fires_on_aging_balances(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
) -> None:
    ids = await _seed_two_managers(property_store)

    await property_store.upsert_tenant(Tenant(
        id="t-aging", name="Late Larry", email="l@test.com",
        balance_owed=Decimal("2000"), balance_30_plus=Decimal("1500"),
    ))
    await property_store.upsert_lease(Lease(
        id="l-aging", unit_id="u-aging", tenant_id="t-aging",
        property_id=ids["prop1"],
        start_date=date.today() - timedelta(days=365),
        end_date=date.today() + timedelta(days=180),
        monthly_rent=Decimal("1000"), status=LeaseStatus.ACTIVE,
    ))
    await property_store.upsert_unit(Unit(
        id="u-aging", property_id=ids["prop1"], unit_number="AG1",
        status=UnitStatus.OCCUPIED,
    ))

    result = await engine.run_all()
    gap_signals = [s for s in result.signals if s.signal_type == "CommunicationGap"]
    assert len(gap_signals) >= 1
    sig = gap_signals[0]
    assert sig.entity_id == "mgr-1"
    situations = sig.evidence["situations"]
    assert any(s["type"] == "aging_balance" for s in situations)


@pytest.mark.asyncio
async def test_communication_gap_fires_on_vacancy_cluster(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
) -> None:
    ids = await _seed_two_managers(property_store)

    for i in range(4):
        await property_store.upsert_unit(Unit(
            id=f"u-vac-{i}", property_id=ids["prop1"], unit_number=f"V{i}",
            status=UnitStatus.VACANT, days_vacant=20,
        ))

    result = await engine.run_all()
    gap_signals = [s for s in result.signals if s.signal_type == "CommunicationGap"]
    mgr1_gaps = [s for s in gap_signals if s.entity_id == "mgr-1"]
    assert len(mgr1_gaps) >= 1
    situations = mgr1_gaps[0].evidence["situations"]
    assert any(s["type"] == "high_vacancy_cluster" for s in situations)


@pytest.mark.asyncio
async def test_communication_gap_no_fire_when_clean(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
) -> None:
    ids = await _seed_two_managers(property_store)

    await property_store.upsert_unit(Unit(
        id="u-ok", property_id=ids["prop1"], unit_number="OK1",
        status=UnitStatus.OCCUPIED,
    ))
    await property_store.upsert_tenant(Tenant(
        id="t-ok", name="Good Guy", email="g@test.com",
        balance_owed=Decimal("0"),
    ))

    result = await engine.run_all()
    gap_signals = [
        s for s in result.signals
        if s.signal_type == "CommunicationGap" and s.entity_id == "mgr-1"
    ]
    assert len(gap_signals) == 0


# =============================================================================
# PolicyBreach
# =============================================================================


@pytest.mark.asyncio
async def test_policy_breach_renewal_not_sent(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
) -> None:
    ids = await _seed_two_managers(property_store)

    await property_store.upsert_unit(Unit(
        id="u-renew", property_id=ids["prop1"], unit_number="R1",
        status=UnitStatus.OCCUPIED,
    ))
    await property_store.upsert_lease(Lease(
        id="l-expiring", unit_id="u-renew", tenant_id="t-renew",
        property_id=ids["prop1"],
        start_date=date.today() - timedelta(days=300),
        end_date=date.today() + timedelta(days=30),
        monthly_rent=Decimal("1200"), status=LeaseStatus.ACTIVE,
    ))

    result = await engine.run_all()
    breach_signals = [s for s in result.signals if s.signal_type == "PolicyBreach"]
    assert len(breach_signals) >= 1
    sig = breach_signals[0]
    assert sig.entity_id == "mgr-1"
    breaches = sig.evidence["breaches"]
    assert any(b["type"] == "renewal_not_sent" for b in breaches)


@pytest.mark.asyncio
async def test_policy_breach_no_fire_when_renewal_pending(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
) -> None:
    ids = await _seed_two_managers(property_store)

    await property_store.upsert_unit(Unit(
        id="u-renew2", property_id=ids["prop1"], unit_number="R2",
        status=UnitStatus.OCCUPIED,
    ))
    await property_store.upsert_lease(Lease(
        id="l-old", unit_id="u-renew2", tenant_id="t-renew2",
        property_id=ids["prop1"],
        start_date=date.today() - timedelta(days=300),
        end_date=date.today() + timedelta(days=30),
        monthly_rent=Decimal("1200"), status=LeaseStatus.ACTIVE,
    ))
    await property_store.upsert_lease(Lease(
        id="l-renewal", unit_id="u-renew2", tenant_id="t-renew2",
        property_id=ids["prop1"],
        start_date=date.today() + timedelta(days=31),
        end_date=date.today() + timedelta(days=395),
        monthly_rent=Decimal("1300"), status=LeaseStatus.PENDING,
    ))

    result = await engine.run_all()
    breach_signals = [s for s in result.signals if s.signal_type == "PolicyBreach"]
    mgr1_breaches = [s for s in breach_signals if s.entity_id == "mgr-1"]
    renewal_breaches = [
        b for s in mgr1_breaches
        for b in s.evidence.get("breaches", [])
        if b["type"] == "renewal_not_sent" and b["unit_id"] == "u-renew2"
    ]
    assert len(renewal_breaches) == 0


@pytest.mark.asyncio
async def test_policy_breach_make_ready_overdue(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
) -> None:
    ids = await _seed_two_managers(property_store)

    await property_store.upsert_unit(Unit(
        id="u-makeready", property_id=ids["prop1"], unit_number="MR1",
        status=UnitStatus.VACANT,
    ))
    await property_store.upsert_maintenance_request(MaintenanceRequest(
        id="maint-1", unit_id="u-makeready", property_id=ids["prop1"],
        title="Paint unit", status=MaintenanceStatus.OPEN, priority=Priority.MEDIUM,
        created_at=datetime.now(UTC) - timedelta(days=20),
    ))

    result = await engine.run_all()
    breach_signals = [s for s in result.signals if s.signal_type == "PolicyBreach"]
    mgr1_breaches = [s for s in breach_signals if s.entity_id == "mgr-1"]
    assert len(mgr1_breaches) >= 1
    breaches = mgr1_breaches[0].evidence["breaches"]
    make_ready = [b for b in breaches if b["type"] == "make_ready_overdue"]
    assert len(make_ready) >= 1
    assert make_ready[0]["unit_id"] == "u-makeready"


