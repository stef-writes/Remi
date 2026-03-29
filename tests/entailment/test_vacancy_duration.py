"""Test VacancyDuration signal detection."""

from __future__ import annotations

from decimal import Decimal

import pytest

from remi.domain.properties.enums import UnitStatus
from remi.domain.properties.models import Unit
from remi.domain.signals.types import Severity
from remi.infrastructure.entailment.engine import EntailmentEngine
from remi.infrastructure.entailment.in_memory_signal_store import InMemorySignalStore
from remi.infrastructure.properties.in_memory import InMemoryPropertyStore
from tests.conftest import seed_basic_portfolio


@pytest.mark.asyncio
async def test_vacancy_fires_above_threshold(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> None:
    ids = await seed_basic_portfolio(property_store)

    await property_store.upsert_unit(Unit(
        id="u-1", property_id=ids["property_id"], unit_number="101",
        status=UnitStatus.VACANT, days_vacant=45, market_rent=Decimal("1500"),
    ))

    result = await engine.run_all()
    sigs = await signal_store.list_signals(signal_type="VacancyDuration")

    assert len(sigs) == 1
    assert sigs[0].entity_id == "u-1"
    assert sigs[0].severity == Severity.MEDIUM
    assert sigs[0].evidence["days_vacant"] == 45


@pytest.mark.asyncio
async def test_vacancy_does_not_fire_below_threshold(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> None:
    ids = await seed_basic_portfolio(property_store)

    await property_store.upsert_unit(Unit(
        id="u-2", property_id=ids["property_id"], unit_number="102",
        status=UnitStatus.VACANT, days_vacant=15, market_rent=Decimal("1200"),
    ))

    await engine.run_all()
    sigs = await signal_store.list_signals(signal_type="VacancyDuration")
    assert len(sigs) == 0


@pytest.mark.asyncio
async def test_vacancy_ignores_occupied_units(
    engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> None:
    ids = await seed_basic_portfolio(property_store)

    await property_store.upsert_unit(Unit(
        id="u-3", property_id=ids["property_id"], unit_number="103",
        status=UnitStatus.OCCUPIED, days_vacant=None, market_rent=Decimal("1300"),
    ))

    await engine.run_all()
    sigs = await signal_store.list_signals(signal_type="VacancyDuration")
    assert len(sigs) == 0
