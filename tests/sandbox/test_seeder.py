"""Test SandboxSeeder — data export into sandbox sessions."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from remi.domain.properties.enums import (
    LeaseStatus,
    MaintenanceStatus,
    UnitStatus,
)
from remi.domain.properties.models import (
    Address,
    Lease,
    MaintenanceRequest,
    Portfolio,
    Property,
    PropertyManager,
    Tenant,
    Unit,
)
from remi.domain.signals.types import Severity, EntityType, Provenance, Signal
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
async def test_seed_empty_stores(
    seeder: SandboxSeeder,
    sandbox: LocalSandbox,
) -> None:
    session = await sandbox.create_session("test-empty")
    files = await seeder.seed(sandbox, "test-empty")

    assert "managers.csv" in files
    assert "signals.json" in files
    assert "README.txt" in files
    assert len(files) == 10  # 7 CSV + signals.json + remi_client.py + README.txt

    content = await sandbox.read_file("test-empty", "managers.csv")
    assert content is not None
    assert content == ""  # empty store -> empty CSV (no headers without rows)


@pytest.mark.asyncio
async def test_seed_with_data(
    seeder: SandboxSeeder,
    sandbox: LocalSandbox,
    property_store: InMemoryPropertyStore,
) -> None:
    mgr = PropertyManager(id="mgr-1", name="Alice", email="a@test.com")
    await property_store.upsert_manager(mgr)

    pf = Portfolio(id="pf-1", manager_id="mgr-1", name="Main Portfolio")
    await property_store.upsert_portfolio(pf)

    prop = Property(id="prop-1", portfolio_id="pf-1", name="Oak Tower", address=_ADDR)
    await property_store.upsert_property(prop)

    unit = Unit(id="u-1", property_id="prop-1", unit_number="101", status=UnitStatus.OCCUPIED)
    await property_store.upsert_unit(unit)

    session = await sandbox.create_session("test-data")
    files = await seeder.seed(sandbox, "test-data")

    managers_csv = await sandbox.read_file("test-data", "managers.csv")
    assert managers_csv is not None
    reader = csv.DictReader(io.StringIO(managers_csv))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["name"] == "Alice"

    properties_csv = await sandbox.read_file("test-data", "properties.csv")
    assert properties_csv is not None
    reader = csv.DictReader(io.StringIO(properties_csv))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["name"] == "Oak Tower"

    units_csv = await sandbox.read_file("test-data", "units.csv")
    assert units_csv is not None
    reader = csv.DictReader(io.StringIO(units_csv))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["unit_number"] == "101"


@pytest.mark.asyncio
async def test_seed_signals(
    seeder: SandboxSeeder,
    sandbox: LocalSandbox,
    signal_store: InMemorySignalStore,
) -> None:
    signal = Signal(
        signal_id="sig-1",
        signal_type="VacancyDuration",
        severity=Severity.HIGH,
        entity_type=EntityType.UNIT,
        entity_id="u-1",
        entity_name="Unit 101",
        description="Vacant for 45 days",
        evidence={"days_vacant": 45},
    )
    await signal_store.put_signal(signal)

    session = await sandbox.create_session("test-signals")
    await seeder.seed(sandbox, "test-signals")

    content = await sandbox.read_file("test-signals", "signals.json")
    assert content is not None
    data = json.loads(content)
    assert len(data) == 1
    assert data[0]["signal_type"] == "VacancyDuration"
    assert data[0]["evidence"]["days_vacant"] == 45


@pytest.mark.asyncio
async def test_readme_written(
    seeder: SandboxSeeder,
    sandbox: LocalSandbox,
) -> None:
    session = await sandbox.create_session("test-readme")
    await seeder.seed(sandbox, "test-readme")

    readme = await sandbox.read_file("test-readme", "README.txt")
    assert readme is not None
    assert "REMI Sandbox Data Files" in readme
    assert "managers.csv" in readme
    assert "signals.json" in readme
    assert "remi_client" in readme


@pytest.mark.asyncio
async def test_remi_client_seeded(
    seeder: SandboxSeeder,
    sandbox: LocalSandbox,
) -> None:
    await sandbox.create_session("test-client")
    files = await seeder.seed(sandbox, "test-client")

    assert "remi_client.py" in files

    content = await sandbox.read_file("test-client", "remi_client.py")
    assert content is not None
    assert "class _RemiClient" in content
    assert "remi = _RemiClient()" in content
    assert "from remi_client import remi" in content
