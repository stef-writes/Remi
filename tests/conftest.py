"""Shared test fixtures for the signal-layer test suite."""

from __future__ import annotations

import pytest

from remi.domain.evaluators.engine import EntailmentEngine
from remi.domain.ontology.schema import load_domain_yaml
from remi.domain.portfolio.models import (
    Address,
    Portfolio,
    Property,
    PropertyManager,
)
from remi.agent.signals import DomainTBox
from remi.domain.stores.mem import InMemoryPropertyStore
from remi.agent.signals.mem import InMemorySignalStore


@pytest.fixture
def domain_tbox() -> DomainTBox:
    raw = load_domain_yaml()
    return DomainTBox.from_yaml(raw)


@pytest.fixture
def signal_store() -> InMemorySignalStore:
    return InMemorySignalStore()


@pytest.fixture
def property_store() -> InMemoryPropertyStore:
    return InMemoryPropertyStore()


@pytest.fixture
def engine(
    domain_tbox: DomainTBox,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> EntailmentEngine:
    return EntailmentEngine(
        domain=domain_tbox,
        property_store=property_store,
        signal_store=signal_store,
    )


# ---------------------------------------------------------------------------
# Fixture data helpers
# ---------------------------------------------------------------------------

_ADDR = Address(street="100 Smithfield St", city="Pittsburgh", state="PA", zip_code="15222")


async def seed_basic_portfolio(ps: InMemoryPropertyStore) -> dict[str, str]:
    """Seed one manager -> one portfolio -> one property.

    Returns a dict of entity IDs for convenience.
    """
    mgr = PropertyManager(id="mgr-1", name="Jake Kraus", email="jake@rivaridge.com")
    await ps.upsert_manager(mgr)

    pf = Portfolio(id="pf-1", manager_id="mgr-1", name="Kraus Portfolio")
    await ps.upsert_portfolio(pf)

    prop = Property(id="prop-1", portfolio_id="pf-1", name="100 Smithfield St", address=_ADDR)
    await ps.upsert_property(prop)

    return {"manager_id": "mgr-1", "portfolio_id": "pf-1", "property_id": "prop-1"}
