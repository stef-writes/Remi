"""Tests for the CompositionProducer — composite signals from co-occurring constituents."""

from __future__ import annotations

import pytest

from remi.knowledge.entailment.composition import CompositionProducer
from remi.knowledge.composite import CompositeProducer
from remi.models.signals import (
    CompositionRule,
    DomainRulebook,
    MutableRulebook,
    ProducerResult,
    Severity,
    Signal,
    SignalProducer,
)
from remi.models.ontology import KnowledgeProvenance
from remi.stores.signals import InMemorySignalStore


@pytest.fixture
def signal_store() -> InMemorySignalStore:
    return InMemorySignalStore()


def _make_signal(
    signal_type: str,
    entity_id: str,
    entity_type: str = "PropertyManager",
    entity_name: str = "Alice Manager",
    severity: Severity = Severity.HIGH,
) -> Signal:
    return Signal(
        signal_id=f"signal:{signal_type.lower()}:{entity_id}",
        signal_type=signal_type,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        description=f"{signal_type} on {entity_name}",
    )


def _make_rulebook(*rules: CompositionRule) -> DomainRulebook:
    return DomainRulebook(compositions=list(rules))


def _delinquency_lease_cliff_rule() -> CompositionRule:
    return CompositionRule(
        name="DelinquencyLeaseCliff",
        description="Compounding cash flow risk",
        constituents=["DelinquencyConcentration", "LeaseExpirationCliff"],
        scope="PropertyManager",
        severity=Severity.CRITICAL,
        require_same_entity=True,
    )


# -- Basic composition -------------------------------------------------------


async def test_composition_fires_when_all_constituents_present(
    signal_store: InMemorySignalStore,
) -> None:
    await signal_store.put_signal(
        _make_signal("DelinquencyConcentration", "mgr-1")
    )
    await signal_store.put_signal(
        _make_signal("LeaseExpirationCliff", "mgr-1")
    )

    producer = CompositionProducer(
        domain=_make_rulebook(_delinquency_lease_cliff_rule()),
        signal_store=signal_store,
    )
    result = await producer.evaluate()

    assert result.produced == 1
    composite = result.signals[0]
    assert composite.signal_type == "DelinquencyLeaseCliff"
    assert composite.severity == Severity.CRITICAL
    assert composite.entity_id == "mgr-1"
    assert composite.entity_type == "PropertyManager"
    assert "constituent_signal_ids" in composite.evidence
    assert len(composite.evidence["constituent_signal_ids"]) == 2


async def test_composition_does_not_fire_with_partial_constituents(
    signal_store: InMemorySignalStore,
) -> None:
    await signal_store.put_signal(
        _make_signal("DelinquencyConcentration", "mgr-1")
    )

    producer = CompositionProducer(
        domain=_make_rulebook(_delinquency_lease_cliff_rule()),
        signal_store=signal_store,
    )
    result = await producer.evaluate()
    assert result.produced == 0


async def test_composition_does_not_fire_across_different_entities(
    signal_store: InMemorySignalStore,
) -> None:
    await signal_store.put_signal(
        _make_signal("DelinquencyConcentration", "mgr-1")
    )
    await signal_store.put_signal(
        _make_signal("LeaseExpirationCliff", "mgr-2")
    )

    producer = CompositionProducer(
        domain=_make_rulebook(_delinquency_lease_cliff_rule()),
        signal_store=signal_store,
    )
    result = await producer.evaluate()
    assert result.produced == 0


async def test_composition_respects_scope_filter(
    signal_store: InMemorySignalStore,
) -> None:
    """Signals on wrong entity type don't match even if type names match."""
    await signal_store.put_signal(
        _make_signal("DelinquencyConcentration", "unit-1", entity_type="Unit")
    )
    await signal_store.put_signal(
        _make_signal("LeaseExpirationCliff", "unit-1", entity_type="Unit")
    )

    producer = CompositionProducer(
        domain=_make_rulebook(_delinquency_lease_cliff_rule()),
        signal_store=signal_store,
    )
    result = await producer.evaluate()
    assert result.produced == 0


async def test_composition_fires_on_multiple_entities(
    signal_store: InMemorySignalStore,
) -> None:
    for mgr_id in ["mgr-1", "mgr-2"]:
        await signal_store.put_signal(
            _make_signal("DelinquencyConcentration", mgr_id)
        )
        await signal_store.put_signal(
            _make_signal("LeaseExpirationCliff", mgr_id)
        )

    producer = CompositionProducer(
        domain=_make_rulebook(_delinquency_lease_cliff_rule()),
        signal_store=signal_store,
    )
    result = await producer.evaluate()
    assert result.produced == 2

    entity_ids = {s.entity_id for s in result.signals}
    assert entity_ids == {"mgr-1", "mgr-2"}


async def test_composition_with_no_rules(
    signal_store: InMemorySignalStore,
) -> None:
    await signal_store.put_signal(_make_signal("Anything", "mgr-1"))

    producer = CompositionProducer(
        domain=_make_rulebook(),
        signal_store=signal_store,
    )
    result = await producer.evaluate()
    assert result.produced == 0


async def test_composition_with_empty_store(
    signal_store: InMemorySignalStore,
) -> None:
    producer = CompositionProducer(
        domain=_make_rulebook(_delinquency_lease_cliff_rule()),
        signal_store=signal_store,
    )
    result = await producer.evaluate()
    assert result.produced == 0


async def test_composition_uses_data_derived_provenance(
    signal_store: InMemorySignalStore,
) -> None:
    await signal_store.put_signal(
        _make_signal("DelinquencyConcentration", "mgr-1")
    )
    await signal_store.put_signal(
        _make_signal("LeaseExpirationCliff", "mgr-1")
    )

    producer = CompositionProducer(
        domain=_make_rulebook(_delinquency_lease_cliff_rule()),
        signal_store=signal_store,
    )
    result = await producer.evaluate()
    assert result.signals[0].provenance == KnowledgeProvenance.DATA_DERIVED


# -- MutableRulebook support --------------------------------------------------


async def test_composition_works_with_mutable_rulebook(
    signal_store: InMemorySignalStore,
) -> None:
    base = DomainRulebook()
    mutable = MutableRulebook(base)
    mutable.add_composition(_delinquency_lease_cliff_rule())

    await signal_store.put_signal(
        _make_signal("DelinquencyConcentration", "mgr-1")
    )
    await signal_store.put_signal(
        _make_signal("LeaseExpirationCliff", "mgr-1")
    )

    producer = CompositionProducer(domain=mutable, signal_store=signal_store)
    result = await producer.evaluate()
    assert result.produced == 1


# -- Integration with CompositeProducer pipeline ------------------------------


class _FixedProducer(SignalProducer):
    def __init__(self, name: str, signals: list[Signal]) -> None:
        self._name = name
        self._signals = signals

    @property
    def name(self) -> str:
        return self._name

    async def evaluate(self) -> ProducerResult:
        return ProducerResult(
            source=self._name,
            signals=list(self._signals),
            produced=len(self._signals),
        )


async def test_composition_in_composite_pipeline(
    signal_store: InMemorySignalStore,
) -> None:
    """CompositionProducer reads signals written by earlier producers."""
    sig_a = _make_signal("DelinquencyConcentration", "mgr-1")
    sig_b = _make_signal("LeaseExpirationCliff", "mgr-1")

    composition_producer = CompositionProducer(
        domain=_make_rulebook(_delinquency_lease_cliff_rule()),
        signal_store=signal_store,
    )

    pipeline = CompositeProducer(
        signal_store=signal_store,
        producers=[
            _FixedProducer("rule_engine", [sig_a, sig_b]),
            composition_producer,
        ],
    )

    result = await pipeline.run_all()
    assert result.produced == 3

    stored = await signal_store.list_signals()
    types = {s.signal_type for s in stored}
    assert "DelinquencyConcentration" in types
    assert "LeaseExpirationCliff" in types
    assert "DelinquencyLeaseCliff" in types
