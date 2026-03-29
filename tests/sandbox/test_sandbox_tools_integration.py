"""Integration test — seed sandbox then run Python that reads the CSV data."""

from __future__ import annotations

from pathlib import Path

import pytest

from remi.domain.properties.enums import UnitStatus
from remi.domain.properties.models import (
    Address,
    Portfolio,
    Property,
    PropertyManager,
    Unit,
)
from remi.domain.sandbox.types import ExecStatus
from remi.infrastructure.entailment.in_memory_signal_store import InMemorySignalStore
from remi.infrastructure.properties.in_memory import InMemoryPropertyStore
from remi.infrastructure.sandbox.local import LocalSandbox
from remi.infrastructure.sandbox.seeder import SandboxSeeder

_ADDR = Address(street="100 Main St", city="Portland", state="OR", zip_code="97201")


@pytest.fixture
def property_store() -> InMemoryPropertyStore:
    return InMemoryPropertyStore()


@pytest.fixture
def signal_store() -> InMemorySignalStore:
    return InMemorySignalStore()


@pytest.fixture
def sandbox(tmp_path: Path) -> LocalSandbox:
    return LocalSandbox(root=tmp_path / "sandbox")


@pytest.fixture
def seeder(property_store: InMemoryPropertyStore, signal_store: InMemorySignalStore) -> SandboxSeeder:
    return SandboxSeeder(property_store=property_store, signal_store=signal_store)


@pytest.mark.asyncio
async def test_seed_then_exec_python(
    seeder: SandboxSeeder,
    sandbox: LocalSandbox,
    property_store: InMemoryPropertyStore,
) -> None:
    """Seed real data, then run a Python script that reads a CSV and computes."""
    mgr = PropertyManager(id="mgr-1", name="Alice", email="a@test.com")
    await property_store.upsert_manager(mgr)

    pf = Portfolio(id="pf-1", manager_id="mgr-1", name="Main Portfolio")
    await property_store.upsert_portfolio(pf)

    prop = Property(id="prop-1", portfolio_id="pf-1", name="Oak Tower", address=_ADDR)
    await property_store.upsert_property(prop)

    for i in range(5):
        status = UnitStatus.OCCUPIED if i < 3 else UnitStatus.VACANT
        unit = Unit(id=f"u-{i}", property_id="prop-1", unit_number=str(100 + i), status=status)
        await property_store.upsert_unit(unit)

    session = await sandbox.create_session("integ-1")
    await seeder.seed(sandbox, "integ-1")

    script = """\
import csv

with open("units.csv") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total = len(rows)
occupied = sum(1 for r in rows if r["status"] == "occupied")
print(f"total={total}")
print(f"occupied={occupied}")
print(f"occupancy={occupied/total*100:.0f}%")
"""

    result = await sandbox.exec_python("integ-1", script)
    assert result.status == ExecStatus.SUCCESS
    assert "total=5" in result.stdout
    assert "occupied=3" in result.stdout
    assert "occupancy=60%" in result.stdout


@pytest.mark.asyncio
async def test_seed_then_read_signals_json(
    seeder: SandboxSeeder,
    sandbox: LocalSandbox,
    signal_store: InMemorySignalStore,
) -> None:
    """Seed signals, then run Python that reads and parses signals.json."""
    from remi.domain.signals.types import Severity, EntityType, Signal

    signal = Signal(
        signal_id="sig-1",
        signal_type="VacancyDuration",
        severity=Severity.HIGH,
        entity_type=EntityType.UNIT,
        entity_id="u-1",
        entity_name="Unit 101",
        evidence={"days_vacant": 45},
    )
    await signal_store.put_signal(signal)

    session = await sandbox.create_session("integ-2")
    await seeder.seed(sandbox, "integ-2")

    script = """\
import json

with open("signals.json") as f:
    signals = json.load(f)

print(f"count={len(signals)}")
print(f"type={signals[0]['signal_type']}")
"""

    result = await sandbox.exec_python("integ-2", script)
    assert result.status == ExecStatus.SUCCESS
    assert "count=1" in result.stdout
    assert "type=VacancyDuration" in result.stdout
