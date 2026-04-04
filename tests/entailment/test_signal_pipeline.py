"""Tests for the signal pipeline: SignalProducer, CompositeProducer,
StatisticalProducer, and FeedbackStore.
"""

from __future__ import annotations

import pytest

from remi.agent.signals.producers.composite import CompositeProducer
from remi.application.services.monitoring.signals.engine import EntailmentEngine
from remi.agent.graph.adapters.bridge import BridgedKnowledgeGraph
from remi.agent.signals.producers.statistical import StatisticalProducer
from remi.application.core.models import Unit, UnitStatus
from remi.agent.signals import (
    DomainTBox,
    ProducerResult,
    Provenance,
    Severity,
    Signal,
    SignalFeedback,
    SignalOutcome,
    SignalProducer,
)
from remi.agent.graph.adapters.mem import InMemoryKnowledgeStore
from remi.application.infra.stores.mem import InMemoryPropertyStore
from remi.agent.signals.persistence.mem import InMemoryFeedbackStore, InMemorySignalStore

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def signal_store() -> InMemorySignalStore:
    return InMemorySignalStore()


@pytest.fixture
def feedback_store() -> InMemoryFeedbackStore:
    return InMemoryFeedbackStore()


@pytest.fixture
def property_store() -> InMemoryPropertyStore:
    return InMemoryPropertyStore()


@pytest.fixture
def knowledge_graph(
    property_store: InMemoryPropertyStore,
) -> BridgedKnowledgeGraph:
    ks = InMemoryKnowledgeStore()
    return BridgedKnowledgeGraph(
        ks,
        core_types={
            "PropertyManager": (property_store.get_manager, property_store.list_managers),
            "Portfolio": (property_store.get_portfolio, property_store.list_portfolios),
            "Property": (property_store.get_property, property_store.list_properties),
            "Unit": (property_store.get_unit, property_store.list_units),
            "Lease": (property_store.get_lease, property_store.list_leases),
            "Tenant": (property_store.get_tenant, property_store.list_tenants),
            "MaintenanceRequest": (
                property_store.get_maintenance_request,
                property_store.list_maintenance_requests,
            ),
        },
    )


# -- Helpers ------------------------------------------------------------------


class _FixedProducer(SignalProducer):
    """Test producer that returns fixed signals."""

    def __init__(self, producer_name: str, signals: list[Signal]) -> None:
        self._name = producer_name
        self._signals = signals

    @property
    def name(self) -> str:
        return self._name

    async def evaluate(self) -> ProducerResult:
        result = ProducerResult(source=self.name)
        result.signals = list(self._signals)
        result.produced = len(self._signals)
        return result


class _FailingProducer(SignalProducer):
    """Test producer that always raises."""

    @property
    def name(self) -> str:
        return "failing"

    async def evaluate(self) -> ProducerResult:
        raise RuntimeError("boom")


def _make_signal(
    signal_id: str = "sig-1",
    signal_type: str = "TestSignal",
    severity: Severity = Severity.LOW,
    entity_type: str = "TestEntity",
    entity_id: str = "e-1",
) -> Signal:
    return Signal(
        signal_id=signal_id,
        signal_type=signal_type,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
        description="test signal",
    )


# -- SignalProducer interface -------------------------------------------------


async def test_signal_producer_interface() -> None:
    sig = _make_signal()
    producer = _FixedProducer("test", [sig])

    assert producer.name == "test"
    result = await producer.evaluate()
    assert result.produced == 1
    assert len(result.signals) == 1
    assert result.signals[0].signal_id == "sig-1"


async def test_signal_accepts_arbitrary_entity_type() -> None:
    """Signal.entity_type is open — any string works."""
    sig = Signal(
        signal_id="s-1",
        signal_type="CustomDomainSignal",
        severity=Severity.HIGH,
        entity_type="PatientRecord",
        entity_id="patient-42",
        description="Custom domain signal",
    )
    assert sig.entity_type == "PatientRecord"


# -- CompositeProducer -------------------------------------------------------


async def test_composite_runs_all_producers(
    signal_store: InMemorySignalStore,
) -> None:
    sig_a = _make_signal(signal_id="a-1", signal_type="TypeA")
    sig_b = _make_signal(signal_id="b-1", signal_type="TypeB")

    composite = CompositeProducer(
        signal_store=signal_store,
        producers=[
            _FixedProducer("source_a", [sig_a]),
            _FixedProducer("source_b", [sig_b]),
        ],
    )

    result = await composite.run_all()
    assert result.produced == 2
    assert len(result.signals) == 2
    assert "source_a" in result.per_source
    assert "source_b" in result.per_source

    stored = await signal_store.list_signals()
    assert len(stored) == 2


async def test_composite_deduplicates_by_signal_id(
    signal_store: InMemorySignalStore,
) -> None:
    sig = _make_signal(signal_id="same-id")

    composite = CompositeProducer(
        signal_store=signal_store,
        producers=[
            _FixedProducer("first", [sig]),
            _FixedProducer("second", [sig]),
        ],
    )

    result = await composite.run_all()
    assert result.produced == 1

    stored = await signal_store.list_signals()
    assert len(stored) == 1


async def test_composite_survives_failing_producer(
    signal_store: InMemorySignalStore,
) -> None:
    sig = _make_signal()

    composite = CompositeProducer(
        signal_store=signal_store,
        producers=[
            _FailingProducer(),
            _FixedProducer("healthy", [sig]),
        ],
    )

    result = await composite.run_all()
    assert result.produced == 1
    assert "healthy" in result.per_source


async def test_composite_clears_store_before_run(
    signal_store: InMemorySignalStore,
) -> None:
    old_sig = _make_signal(signal_id="old")
    await signal_store.put_signal(old_sig)

    composite = CompositeProducer(
        signal_store=signal_store,
        producers=[_FixedProducer("new", [_make_signal(signal_id="new")])],
    )

    await composite.run_all()
    stored = await signal_store.list_signals()
    ids = {s.signal_id for s in stored}
    assert "new" in ids
    assert "old" not in ids


# -- EntailmentEngine as SignalProducer ---------------------------------------


async def test_entailment_engine_implements_signal_producer(
    property_store: InMemoryPropertyStore,
) -> None:
    """EntailmentEngine is a valid SignalProducer."""
    from remi.application.infra.ontology.schema import load_domain_yaml

    domain = DomainTBox.from_yaml(load_domain_yaml())
    engine = EntailmentEngine(domain=domain, property_store=property_store)

    assert isinstance(engine, SignalProducer)
    assert engine.name == "rule_engine"

    result = await engine.evaluate()
    assert isinstance(result, ProducerResult)
    assert result.source == "rule_engine"


# -- StatisticalProducer ------------------------------------------------------


async def test_statistical_producer_empty_store(
    knowledge_graph: BridgedKnowledgeGraph,
) -> None:
    """No data → no signals."""
    await _bootstrap(knowledge_graph)
    producer = StatisticalProducer(knowledge_graph=knowledge_graph)
    result = await producer.evaluate()
    assert result.produced == 0


async def test_statistical_outlier_detection(
    knowledge_graph: BridgedKnowledgeGraph,
    property_store: InMemoryPropertyStore,
) -> None:
    """Seed units with one outlier value, verify detection."""
    await _bootstrap(knowledge_graph)

    for i in range(10):
        unit = Unit(
            id=f"u-{i}",
            property_id="prop-1",
            unit_number=str(100 + i),
            status=UnitStatus.OCCUPIED,
            days_vacant=5,
        )
        await property_store.upsert_unit(unit)

    outlier = Unit(
        id="u-outlier",
        property_id="prop-1",
        unit_number="999",
        status=UnitStatus.VACANT,
        days_vacant=200,
    )
    await property_store.upsert_unit(outlier)

    producer = StatisticalProducer(
        knowledge_graph=knowledge_graph,
        zscore_threshold=2.0,
        min_sample_size=5,
    )
    result = await producer.evaluate()

    outlier_signals = [
        s for s in result.signals if "outlier" in s.signal_id.lower() and "u-outlier" in s.signal_id
    ]
    assert len(outlier_signals) >= 1, (
        f"Expected at least 1 outlier signal for u-outlier, "
        f"got {result.produced} total signals: "
        f"{[s.signal_id for s in result.signals]}"
    )

    sig = outlier_signals[0]
    assert sig.provenance == Provenance.DATA_DERIVED
    assert "outlier" in sig.signal_type.lower() or "Outlier" in sig.signal_type


# -- FeedbackStore ------------------------------------------------------------


async def test_feedback_record_and_retrieve(
    feedback_store: InMemoryFeedbackStore,
) -> None:
    fb = SignalFeedback(
        feedback_id="fb-1",
        signal_id="sig-1",
        signal_type="VacancyDuration",
        outcome=SignalOutcome.ACTED_ON,
        actor="director",
        notes="Contacted manager",
    )
    await feedback_store.record_feedback(fb)

    retrieved = await feedback_store.get_feedback("fb-1")
    assert retrieved is not None
    assert retrieved.outcome == SignalOutcome.ACTED_ON


async def test_feedback_list_by_signal(
    feedback_store: InMemoryFeedbackStore,
) -> None:
    for i, outcome in enumerate(
        [
            SignalOutcome.ACTED_ON,
            SignalOutcome.DISMISSED,
            SignalOutcome.ACKNOWLEDGED,
        ]
    ):
        fb = SignalFeedback(
            feedback_id=f"fb-{i}",
            signal_id="sig-1",
            signal_type="VacancyDuration",
            outcome=outcome,
        )
        await feedback_store.record_feedback(fb)

    all_fb = await feedback_store.list_feedback(signal_id="sig-1")
    assert len(all_fb) == 3

    acted = await feedback_store.list_feedback(
        signal_id="sig-1",
        outcome="acted_on",
    )
    assert len(acted) == 1


async def test_feedback_summary(
    feedback_store: InMemoryFeedbackStore,
) -> None:
    for i, outcome in enumerate(
        [
            SignalOutcome.ACTED_ON,
            SignalOutcome.ACTED_ON,
            SignalOutcome.DISMISSED,
            SignalOutcome.ACKNOWLEDGED,
            SignalOutcome.FALSE_POSITIVE,
        ]
    ):
        fb = SignalFeedback(
            feedback_id=f"fb-{i}",
            signal_id=f"sig-{i}",
            signal_type="TestSignal",
            outcome=outcome,
        )
        await feedback_store.record_feedback(fb)

    summary = await feedback_store.summarize("TestSignal")
    assert summary.total_feedback == 5
    assert summary.act_rate == 0.4
    assert summary.dismiss_rate == 0.4


async def test_feedback_summary_empty(
    feedback_store: InMemoryFeedbackStore,
) -> None:
    summary = await feedback_store.summarize("UnknownSignal")
    assert summary.total_feedback == 0
    assert summary.act_rate == 0.0


# -- Integration: Composite + Feedback pipeline ------------------------------


async def test_full_pipeline_integration(
    signal_store: InMemorySignalStore,
    feedback_store: InMemoryFeedbackStore,
    property_store: InMemoryPropertyStore,
    knowledge_graph: BridgedKnowledgeGraph,
) -> None:
    """End-to-end: rules + stats produce signals, feedback records outcomes."""
    from remi.application.infra.ontology.schema import load_domain_yaml

    await _bootstrap(knowledge_graph)

    domain = DomainTBox.from_yaml(load_domain_yaml())
    engine = EntailmentEngine(domain=domain, property_store=property_store)
    stats = StatisticalProducer(knowledge_graph=knowledge_graph)

    pipeline = CompositeProducer(
        signal_store=signal_store,
        producers=[engine, stats],
    )

    result = await pipeline.run_all()
    assert isinstance(result.produced, int)
    assert "rule_engine" in result.per_source
    assert "statistical" in result.per_source

    if result.signals:
        sig = result.signals[0]
        fb = SignalFeedback(
            feedback_id="fb-integration",
            signal_id=sig.signal_id,
            signal_type=sig.signal_type,
            outcome=SignalOutcome.ACTED_ON,
            actor="test",
        )
        await feedback_store.record_feedback(fb)
        summary = await feedback_store.summarize(sig.signal_type)
        assert summary.total_feedback >= 1


# -- Helpers ------------------------------------------------------------------


async def _bootstrap(knowledge_graph: BridgedKnowledgeGraph) -> None:
    from remi.application.infra.ontology.seed import seed_knowledge_graph

    await seed_knowledge_graph(knowledge_graph)
