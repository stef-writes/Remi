"""Test that the EntailmentEngine produces traces when a tracer is provided."""

from __future__ import annotations

from decimal import Decimal

import pytest

from remi.knowledge.entailment.engine import EntailmentEngine
from remi.knowledge.ontology.bootstrap import load_domain_yaml
from remi.models.properties import Unit, UnitStatus
from remi.models.signals import DomainRulebook
from remi.observability.tracer import Tracer
from remi.stores.properties import InMemoryPropertyStore
from remi.stores.signals import InMemorySignalStore
from remi.stores.trace import InMemoryTraceStore
from tests.conftest import seed_basic_portfolio


@pytest.fixture
def trace_store() -> InMemoryTraceStore:
    return InMemoryTraceStore()


@pytest.fixture
def tracer(trace_store: InMemoryTraceStore) -> Tracer:
    return Tracer(trace_store)


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
def traced_engine(
    domain_rulebook: DomainRulebook,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
    tracer: Tracer,
) -> EntailmentEngine:
    return EntailmentEngine(
        domain=domain_rulebook,
        property_store=property_store,
        signal_store=signal_store,
        tracer=tracer,
    )


@pytest.mark.asyncio
async def test_entailment_produces_trace(
    traced_engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    trace_store: InMemoryTraceStore,
) -> None:
    ids = await seed_basic_portfolio(property_store)
    await property_store.upsert_unit(Unit(
        id="u-1", property_id=ids["property_id"], unit_number="101",
        status=UnitStatus.VACANT, days_vacant=45, market_rent=Decimal("1500"),
    ))

    result = await traced_engine.run_all()

    assert result.trace_id is not None

    traces = await trace_store.list_traces()
    assert len(traces) == 1
    assert traces[0].trace_id == result.trace_id

    spans = await trace_store.list_spans(result.trace_id)
    assert len(spans) > 1

    root = next(s for s in spans if s.parent_span_id is None)
    assert root.name == "entailment.run_all"
    assert root.kind.value == "entailment"

    evaluator_spans = [s for s in spans if s.parent_span_id == root.span_id]
    assert len(evaluator_spans) > 0

    vacancy_spans = [s for s in evaluator_spans if "VacancyDuration" in s.name]
    assert len(vacancy_spans) == 1
    vs = vacancy_spans[0]
    assert vs.attributes.get("signals_produced", 0) > 0
    assert any(e.name == "signal_produced" for e in vs.events)


@pytest.mark.asyncio
async def test_entailment_trace_has_tbox_metadata(
    traced_engine: EntailmentEngine,
    property_store: InMemoryPropertyStore,
    trace_store: InMemoryTraceStore,
) -> None:
    await seed_basic_portfolio(property_store)
    result = await traced_engine.run_all()
    assert result.trace_id is not None

    spans = await trace_store.list_spans(result.trace_id)
    root = next(s for s in spans if s.parent_span_id is None)

    assert root.attributes.get("signal_definitions", 0) > 0
    assert isinstance(root.attributes.get("thresholds"), dict)


@pytest.mark.asyncio
async def test_untraced_engine_still_works(
    domain_rulebook: DomainRulebook,
    property_store: InMemoryPropertyStore,
    signal_store: InMemorySignalStore,
) -> None:
    """Engine without tracer should work exactly as before."""
    engine = EntailmentEngine(
        domain=domain_rulebook,
        property_store=property_store,
        signal_store=signal_store,
    )
    ids = await seed_basic_portfolio(property_store)
    await property_store.upsert_unit(Unit(
        id="u-1", property_id=ids["property_id"], unit_number="101",
        status=UnitStatus.VACANT, days_vacant=45, market_rent=Decimal("1500"),
    ))

    result = await engine.run_all()
    assert result.trace_id is None
    assert result.produced > 0
