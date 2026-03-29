"""Test LeaseExpirationCliff signal detection."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from remi.domain.properties.enums import LeaseStatus
from remi.domain.properties.models import Lease, Unit
from remi.domain.signals.types import Severity
from remi.infrastructure.entailment.engine import EntailmentEngine
from remi.infrastructure.entailment.in_memory_signal_store import InMemorySignalStore
from remi.infrastructure.properties.in_memory import InMemoryPropertyStore
from tests.conftest import seed_basic_portfolio


@pytest.mark.asyncio
async def test_lease_cliff_fires_above_threshold(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> None:
    """When >30% of active leases expire within 60 days, signal should fire."""
    ids = await seed_basic_portfolio(property_store)
    today = date.today()

    for i in range(3):
        await property_store.upsert_unit(Unit(
            id=f"u-{i}", property_id=ids["property_id"], unit_number=str(100 + i),
        ))
        await property_store.upsert_lease(Lease(
            id=f"l-{i}", unit_id=f"u-{i}", tenant_id=f"t-{i}",
            property_id=ids["property_id"],
            start_date=today - timedelta(days=365),
            end_date=today + timedelta(days=30),
            monthly_rent=Decimal("1000"),
            status=LeaseStatus.ACTIVE,
        ))

    await property_store.upsert_unit(Unit(
        id="u-safe", property_id=ids["property_id"], unit_number="999",
    ))
    await property_store.upsert_lease(Lease(
        id="l-safe", unit_id="u-safe", tenant_id="t-safe",
        property_id=ids["property_id"],
        start_date=today - timedelta(days=365),
        end_date=today + timedelta(days=300),
        monthly_rent=Decimal("1000"),
        status=LeaseStatus.ACTIVE,
    ))

    await engine.run_all()
    sigs = await signal_store.list_signals(signal_type="LeaseExpirationCliff")

    assert len(sigs) == 1
    assert sigs[0].severity == Severity.HIGH
    assert sigs[0].entity_id == "mgr-1"
    assert sigs[0].evidence["expiring_count"] == 3
    assert sigs[0].evidence["total_active"] == 4


@pytest.mark.asyncio
async def test_lease_cliff_does_not_fire_below_threshold(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> None:
    """When <30% of active leases expire within 60 days, no signal."""
    ids = await seed_basic_portfolio(property_store)
    today = date.today()

    for i in range(5):
        await property_store.upsert_unit(Unit(
            id=f"u-{i}", property_id=ids["property_id"], unit_number=str(100 + i),
        ))
        end = today + timedelta(days=30) if i == 0 else today + timedelta(days=200)
        await property_store.upsert_lease(Lease(
            id=f"l-{i}", unit_id=f"u-{i}", tenant_id=f"t-{i}",
            property_id=ids["property_id"],
            start_date=today - timedelta(days=365),
            end_date=end,
            monthly_rent=Decimal("1000"),
            status=LeaseStatus.ACTIVE,
        ))

    await engine.run_all()
    sigs = await signal_store.list_signals(signal_type="LeaseExpirationCliff")
    assert len(sigs) == 0
