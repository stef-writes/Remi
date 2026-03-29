"""Shared test fixtures for the signal-layer test suite."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio

from remi.domain.properties.enums import (
    LeaseStatus,
    MaintenanceStatus,
    OccupancyStatus,
    Priority,
    TenantStatus,
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
from remi.domain.signals.types import DomainOntology
from remi.infrastructure.entailment.engine import EntailmentEngine
from remi.infrastructure.entailment.in_memory_signal_store import InMemorySignalStore
from remi.infrastructure.ontology.bootstrap import load_domain_yaml
from remi.infrastructure.properties.in_memory import InMemoryPropertyStore


@pytest.fixture
def domain_ontology() -> DomainOntology:
    raw = load_domain_yaml()
    return DomainOntology.from_yaml(raw)


@pytest.fixture
def signal_store() -> InMemorySignalStore:
    return InMemorySignalStore()


@pytest.fixture
def property_store() -> InMemoryPropertyStore:
    return InMemoryPropertyStore()


@pytest.fixture
def engine(
    domain_ontology: DomainOntology,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> EntailmentEngine:
    return EntailmentEngine(
        domain=domain_ontology,
        property_store=property_store,
        signal_store=signal_store,
    )


# ---------------------------------------------------------------------------
# Fixture data helpers
# ---------------------------------------------------------------------------

_ADDR = Address(street="100 Main St", city="Portland", state="OR", zip_code="97201")


async def seed_basic_portfolio(ps: InMemoryPropertyStore) -> dict[str, str]:
    """Seed one manager → one portfolio → one property → several units.

    Returns a dict of entity IDs for convenience.
    """
    mgr = PropertyManager(id="mgr-1", name="Alice Manager", email="a@test.com")
    await ps.upsert_manager(mgr)

    pf = Portfolio(id="pf-1", manager_id="mgr-1", name="Main Portfolio")
    await ps.upsert_portfolio(pf)

    prop = Property(id="prop-1", portfolio_id="pf-1", name="Oak Tower", address=_ADDR)
    await ps.upsert_property(prop)

    return {"manager_id": "mgr-1", "portfolio_id": "pf-1", "property_id": "prop-1"}
