"""Test that all produced signals have structurally complete evidence and typed fields."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from remi.application.services.monitoring.signals.engine import EntailmentEngine
from remi.application.core.models import Lease, LeaseStatus, Tenant, TenantStatus, Unit, UnitStatus
from remi.agent.signals import Provenance, Severity, Signal
from remi.application.infra.stores.mem import InMemoryPropertyStore
from remi.agent.signals.persistence.mem import InMemorySignalStore
from tests.conftest import seed_basic_portfolio

REQUIRED_EVIDENCE_FIELDS: dict[str, set[str]] = {
    "VacancyDuration": {"days_vacant", "threshold", "property_id", "unit_number"},
    "LeaseExpirationCliff": {"expiring_count", "total_active", "expiring_pct", "threshold_pct"},
    "DelinquencyConcentration": {
        "delinquency_rate",
        "total_owed",
        "gross_rent_roll",
        "threshold_pct",
    },
    "BelowMarketRent": {"current_rent", "market_rent", "gap_pct", "threshold_pct"},
    "LegalEscalationRisk": {"tenant_status", "balance_owed"},
}


async def _seed_all_signal_types(ps: InMemoryPropertyStore) -> None:
    """Seed data that triggers one of each detectable signal type."""
    ids = await seed_basic_portfolio(ps)
    pid = ids["property_id"]
    today = date.today()

    await ps.upsert_unit(
        Unit(
            id="u-vac",
            property_id=pid,
            unit_number="V01",
            status=UnitStatus.VACANT,
            days_vacant=60,
            market_rent=Decimal("1500"),
        )
    )

    for i in range(3):
        await ps.upsert_unit(
            Unit(
                id=f"u-cliff-{i}",
                property_id=pid,
                unit_number=f"C{i:02d}",
            )
        )
        await ps.upsert_lease(
            Lease(
                id=f"l-cliff-{i}",
                unit_id=f"u-cliff-{i}",
                tenant_id=f"t-cliff-{i}",
                property_id=pid,
                start_date=today - timedelta(days=365),
                end_date=today + timedelta(days=20),
                monthly_rent=Decimal("1000"),
                status=LeaseStatus.ACTIVE,
            )
        )

    await ps.upsert_tenant(
        Tenant(
            id="t-cliff-0",
            name="Dan Morales",
            email="d@test.com",
            balance_owed=Decimal("800"),
        )
    )
    await ps.upsert_tenant(
        Tenant(
            id="t-cliff-1",
            name="Elena Voss",
            email="e@test.com",
        )
    )
    await ps.upsert_tenant(
        Tenant(
            id="t-cliff-2",
            name="Frank Reyes",
            email="f@test.com",
        )
    )

    await ps.upsert_unit(
        Unit(
            id="u-rent",
            property_id=pid,
            unit_number="R01",
            status=UnitStatus.OCCUPIED,
            current_rent=Decimal("800"),
            market_rent=Decimal("1200"),
        )
    )

    await ps.upsert_tenant(
        Tenant(
            id="t-evict",
            name="James Ward",
            email="j@test.com",
            status=TenantStatus.EVICT,
            balance_owed=Decimal("3000"),
        )
    )


@pytest.mark.asyncio
async def test_all_signals_have_required_evidence_fields(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> None:
    await _seed_all_signal_types(property_store)
    result = await engine.run_all()

    assert result.produced > 0, "Should produce at least one signal"

    for sig in result.signals:
        required = REQUIRED_EVIDENCE_FIELDS.get(sig.signal_type)
        if required is None:
            continue
        missing = required - set(sig.evidence.keys())
        assert not missing, (
            f"Signal {sig.signal_type} for {sig.entity_id} missing evidence fields: {missing}"
        )


@pytest.mark.asyncio
async def test_signals_are_typed_pydantic_models(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> None:
    await _seed_all_signal_types(property_store)
    await engine.run_all()

    sigs = await signal_store.list_signals()
    for sig in sigs:
        assert isinstance(sig, Signal)
        assert sig.signal_id
        assert sig.signal_type
        assert isinstance(sig.severity, Severity), (
            f"severity should be Severity enum, got {type(sig.severity)}"
        )
        assert isinstance(sig.entity_type, str), (
            f"entity_type should be str, got {type(sig.entity_type)}"
        )
        assert isinstance(sig.provenance, Provenance), (
            f"provenance should be Provenance enum, got {type(sig.provenance)}"
        )
        assert sig.entity_id
        assert sig.detected_at is not None
