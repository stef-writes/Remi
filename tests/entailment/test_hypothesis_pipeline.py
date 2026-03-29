"""Tests for the hypothesis pipeline: PatternDetector, HypothesisStore,
HypothesisGraduator, and MutableDomainOntology.

The hypothesis pipeline is the induction layer — it discovers candidate
TBox entries from data patterns and graduates them into the live domain.
"""

from __future__ import annotations

import pytest

from remi.domain.signals.hypothesis import (
    Hypothesis,
    HypothesisKind,
    HypothesisStatus,
)
from remi.domain.signals.types import DomainOntology
from remi.infrastructure.entailment.graduation import (
    HypothesisGraduator,
    MutableDomainOntology,
)
from remi.infrastructure.entailment.in_memory_hypothesis_store import (
    InMemoryHypothesisStore,
)
from remi.infrastructure.entailment.pattern_detector import PatternDetector
from remi.infrastructure.memory.in_memory import InMemoryKnowledgeStore
from remi.infrastructure.ontology.bridge import BridgedOntologyStore
from remi.infrastructure.properties.in_memory import InMemoryPropertyStore

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def property_store() -> InMemoryPropertyStore:
    return InMemoryPropertyStore()


@pytest.fixture
def ontology_store(
    property_store: InMemoryPropertyStore,
) -> BridgedOntologyStore:
    ks = InMemoryKnowledgeStore()
    return BridgedOntologyStore(
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


@pytest.fixture
def hypothesis_store() -> InMemoryHypothesisStore:
    return InMemoryHypothesisStore()


@pytest.fixture
def domain() -> DomainOntology:
    from remi.infrastructure.ontology.bootstrap import load_domain_yaml

    return DomainOntology.from_yaml(load_domain_yaml())


@pytest.fixture
def mutable_domain(domain: DomainOntology) -> MutableDomainOntology:
    return MutableDomainOntology(domain)


# -- HypothesisStore ----------------------------------------------------------


async def test_hypothesis_store_put_and_get(
    hypothesis_store: InMemoryHypothesisStore,
) -> None:
    hyp = Hypothesis(
        hypothesis_id="hyp-1",
        kind=HypothesisKind.SIGNAL_DEFINITION,
        title="Test threshold",
        description="Proposed threshold signal",
        confidence=0.85,
        sample_size=100,
        proposed_by="pattern_detector",
    )
    await hypothesis_store.put(hyp)

    retrieved = await hypothesis_store.get("hyp-1")
    assert retrieved is not None
    assert retrieved.title == "Test threshold"
    assert retrieved.status == HypothesisStatus.PROPOSED


async def test_hypothesis_store_list_filters(
    hypothesis_store: InMemoryHypothesisStore,
) -> None:
    for i, kind in enumerate([
        HypothesisKind.SIGNAL_DEFINITION,
        HypothesisKind.CAUSAL_CHAIN,
        HypothesisKind.ANOMALY_PATTERN,
    ]):
        await hypothesis_store.put(Hypothesis(
            hypothesis_id=f"hyp-{i}",
            kind=kind,
            title=f"Hypothesis {i}",
            description="test",
            confidence=0.5 + i * 0.1,
            proposed_by="test",
        ))

    all_hyps = await hypothesis_store.list_hypotheses()
    assert len(all_hyps) == 3

    signals_only = await hypothesis_store.list_hypotheses(
        kind="signal_definition",
    )
    assert len(signals_only) == 1

    high_confidence = await hypothesis_store.list_hypotheses(
        min_confidence=0.65,
    )
    assert len(high_confidence) == 1


async def test_hypothesis_store_update_status(
    hypothesis_store: InMemoryHypothesisStore,
) -> None:
    await hypothesis_store.put(Hypothesis(
        hypothesis_id="hyp-1",
        kind=HypothesisKind.SIGNAL_DEFINITION,
        title="Test",
        description="test",
        confidence=0.8,
        proposed_by="test",
    ))

    updated = await hypothesis_store.update_status(
        "hyp-1",
        HypothesisStatus.CONFIRMED,
        reviewed_by="human",
        review_notes="Looks valid",
    )
    assert updated is not None
    assert updated.status == HypothesisStatus.CONFIRMED
    assert updated.reviewed_by == "human"
    assert updated.reviewed_at is not None


async def test_hypothesis_store_update_nonexistent(
    hypothesis_store: InMemoryHypothesisStore,
) -> None:
    result = await hypothesis_store.update_status(
        "nonexistent", HypothesisStatus.CONFIRMED,
    )
    assert result is None


# -- MutableDomainOntology ----------------------------------------------------


def test_mutable_domain_starts_with_base(
    mutable_domain: MutableDomainOntology,
    domain: DomainOntology,
) -> None:
    assert mutable_domain.all_signal_names() == domain.all_signal_names()
    assert len(mutable_domain.causal_chains) == len(domain.causal_chains)


def test_mutable_domain_add_signal(
    mutable_domain: MutableDomainOntology,
    domain: DomainOntology,
) -> None:
    from remi.domain.signals.types import (
        EntityType,
        Horizon,
        InferenceRule,
        RuleCondition,
        Severity,
        SignalDefinition,
    )

    new_defn = SignalDefinition(
        name="learned_high_rent",
        description="Learned: rent exceeds threshold",
        severity=Severity.MEDIUM,
        entity=EntityType.UNIT,
        horizon=Horizon.CURRENT,
        rule=InferenceRule(
            metric="current_rent",
            condition=RuleCondition.EXCEEDS_THRESHOLD,
            threshold_key="learned:high_rent",
        ),
    )
    mutable_domain.set_threshold("learned:high_rent", 5000.0)
    mutable_domain.add_signal(new_defn)

    assert "learned_high_rent" in mutable_domain.all_signal_names()
    assert "learned_high_rent" not in domain.all_signal_names()
    assert mutable_domain.threshold("learned:high_rent") == 5000.0
    assert mutable_domain.learned_signal_count == 1

    looked_up = mutable_domain.signal("learned_high_rent")
    assert looked_up is not None
    assert looked_up.name == "learned_high_rent"


def test_mutable_domain_add_causal_chain(
    mutable_domain: MutableDomainOntology,
) -> None:
    from remi.domain.signals.types import CausalChain

    chain = CausalChain(
        cause="Unit.sqft",
        effect="Unit.current_rent",
        description="Larger units have higher rent",
    )
    mutable_domain.add_causal_chain(chain)
    assert mutable_domain.learned_chain_count == 1

    parents = mutable_domain.causal_parents("Unit.current_rent")
    assert any(c.cause == "Unit.sqft" for c in parents)


# -- PatternDetector ----------------------------------------------------------


async def test_pattern_detector_empty_store(
    ontology_store: BridgedOntologyStore,
    hypothesis_store: InMemoryHypothesisStore,
) -> None:
    await _bootstrap(ontology_store)
    detector = PatternDetector(ontology_store, hypothesis_store)
    result = await detector.run()
    assert result.proposed == 0
    assert result.errors == 0


async def test_pattern_detector_finds_outlier_threshold(
    ontology_store: BridgedOntologyStore,
    property_store: InMemoryPropertyStore,
    hypothesis_store: InMemoryHypothesisStore,
) -> None:
    """Seed units with one extreme outlier, verify threshold hypothesis."""
    from remi.domain.properties.enums import UnitStatus
    from remi.domain.properties.models import Unit

    await _bootstrap(ontology_store)

    for i in range(10):
        await property_store.upsert_unit(Unit(
            id=f"u-{i}",
            property_id="prop-1",
            unit_number=str(100 + i),
            status=UnitStatus.OCCUPIED,
            days_vacant=5,
        ))

    await property_store.upsert_unit(Unit(
        id="u-outlier",
        property_id="prop-1",
        unit_number="999",
        status=UnitStatus.VACANT,
        days_vacant=200,
    ))

    detector = PatternDetector(
        ontology_store, hypothesis_store,
        zscore_threshold=2.0, min_sample_size=5,
    )
    result = await detector.run()

    threshold_hyps = [
        h for h in result.hypotheses
        if h.kind == HypothesisKind.SIGNAL_DEFINITION
    ]
    assert len(threshold_hyps) >= 1, (
        f"Expected at least 1 threshold hypothesis, "
        f"got {result.proposed} total: "
        f"{[h.title for h in result.hypotheses]}"
    )

    hyp = threshold_hyps[0]
    assert hyp.proposed_by == "pattern_detector"
    assert hyp.confidence > 0
    assert "proposed_threshold" in hyp.evidence

    stored = await hypothesis_store.list_hypotheses()
    assert len(stored) == result.proposed


async def test_pattern_detector_finds_concentration(
    ontology_store: BridgedOntologyStore,
    property_store: InMemoryPropertyStore,
    hypothesis_store: InMemoryHypothesisStore,
) -> None:
    """Seed units where 90% have the same status."""
    from remi.domain.properties.enums import UnitStatus
    from remi.domain.properties.models import Unit

    await _bootstrap(ontology_store)

    for i in range(9):
        await property_store.upsert_unit(Unit(
            id=f"u-{i}",
            property_id="prop-1",
            unit_number=str(100 + i),
            status=UnitStatus.OCCUPIED,
        ))
    await property_store.upsert_unit(Unit(
        id="u-9",
        property_id="prop-1",
        unit_number="109",
        status=UnitStatus.VACANT,
    ))

    detector = PatternDetector(
        ontology_store, hypothesis_store,
        concentration_threshold=0.80, min_sample_size=5,
    )
    result = await detector.run()

    concentration_hyps = [
        h for h in result.hypotheses
        if h.kind == HypothesisKind.ANOMALY_PATTERN
    ]
    assert len(concentration_hyps) >= 1


# -- HypothesisGraduator ----------------------------------------------------


async def test_graduate_signal_definition(
    ontology_store: BridgedOntologyStore,
    hypothesis_store: InMemoryHypothesisStore,
    mutable_domain: MutableDomainOntology,
) -> None:
    """Confirm and graduate a threshold hypothesis into a live SignalDefinition."""
    await _bootstrap(ontology_store)

    hyp = Hypothesis(
        hypothesis_id="hyp-grad-1",
        kind=HypothesisKind.SIGNAL_DEFINITION,
        title="Proposed: Unit.days_vacant outlier",
        description="Threshold signal for days_vacant",
        confidence=0.9,
        sample_size=100,
        proposed_by="pattern_detector",
        proposed_tbox_entry={
            "kind": "signal_definition",
            "name": "Unit_days_vacant_outlier",
            "description": "days_vacant exceeds 50 for Unit",
            "entity": "Unit",
            "rule": {
                "metric": "days_vacant",
                "condition": "exceeds_threshold",
                "threshold_value": 50.0,
            },
        },
    )
    await hypothesis_store.put(hyp)
    await hypothesis_store.update_status(
        "hyp-grad-1", HypothesisStatus.CONFIRMED, reviewed_by="test",
    )

    graduator = HypothesisGraduator(
        mutable_domain, ontology_store, hypothesis_store,
    )
    result = await graduator.graduate("hyp-grad-1")

    assert result.graduated is True
    assert len(result.tbox_entries_created) == 1
    assert result.tbox_entries_created[0]["type"] == "signal_definition"

    assert "Unit_days_vacant_outlier" in mutable_domain.all_signal_names()
    assert mutable_domain.learned_signal_count == 1


async def test_graduate_causal_chain(
    ontology_store: BridgedOntologyStore,
    hypothesis_store: InMemoryHypothesisStore,
    mutable_domain: MutableDomainOntology,
) -> None:
    await _bootstrap(ontology_store)
    initial_chains = len(mutable_domain.causal_chains)

    hyp = Hypothesis(
        hypothesis_id="hyp-grad-2",
        kind=HypothesisKind.CAUSAL_CHAIN,
        title="Correlation: sqft ↔ rent",
        description="Strong positive correlation between sqft and rent",
        confidence=0.85,
        sample_size=200,
        proposed_by="pattern_detector",
        proposed_tbox_entry={
            "kind": "causal_chain",
            "cause": "Unit.sqft",
            "effect": "Unit.current_rent",
            "description": "Positive correlation (r=0.92)",
        },
    )
    await hypothesis_store.put(hyp)
    await hypothesis_store.update_status(
        "hyp-grad-2", HypothesisStatus.CONFIRMED,
    )

    graduator = HypothesisGraduator(
        mutable_domain, ontology_store, hypothesis_store,
    )
    result = await graduator.graduate("hyp-grad-2")

    assert result.graduated is True
    assert len(mutable_domain.causal_chains) == initial_chains + 1


async def test_graduate_rejects_unconfirmed(
    ontology_store: BridgedOntologyStore,
    hypothesis_store: InMemoryHypothesisStore,
    mutable_domain: MutableDomainOntology,
) -> None:
    hyp = Hypothesis(
        hypothesis_id="hyp-unconfirmed",
        kind=HypothesisKind.SIGNAL_DEFINITION,
        title="Not confirmed",
        description="Still proposed",
        confidence=0.5,
        proposed_by="test",
    )
    await hypothesis_store.put(hyp)

    graduator = HypothesisGraduator(
        mutable_domain, ontology_store, hypothesis_store,
    )
    result = await graduator.graduate("hyp-unconfirmed")

    assert result.graduated is False
    assert "proposed" in result.reason


async def test_graduate_all_confirmed(
    ontology_store: BridgedOntologyStore,
    hypothesis_store: InMemoryHypothesisStore,
    mutable_domain: MutableDomainOntology,
) -> None:
    await _bootstrap(ontology_store)

    for i in range(3):
        hyp = Hypothesis(
            hypothesis_id=f"hyp-batch-{i}",
            kind=HypothesisKind.ANOMALY_PATTERN,
            title=f"Pattern {i}",
            description=f"Anomaly pattern {i}",
            confidence=0.7,
            proposed_by="test",
        )
        await hypothesis_store.put(hyp)
        await hypothesis_store.update_status(
            f"hyp-batch-{i}", HypothesisStatus.CONFIRMED,
        )

    graduator = HypothesisGraduator(
        mutable_domain, ontology_store, hypothesis_store,
    )
    results = await graduator.graduate_all_confirmed()
    graduated = [r for r in results if r.graduated]
    assert len(graduated) == 3


# -- End-to-end: detect → confirm → graduate → evaluate ---------------------


async def test_full_hypothesis_lifecycle(
    ontology_store: BridgedOntologyStore,
    property_store: InMemoryPropertyStore,
    hypothesis_store: InMemoryHypothesisStore,
    mutable_domain: MutableDomainOntology,
) -> None:
    """Full cycle: detect patterns → confirm → graduate → verify in TBox."""
    from remi.domain.properties.enums import UnitStatus
    from remi.domain.properties.models import Unit

    await _bootstrap(ontology_store)

    for i in range(10):
        await property_store.upsert_unit(Unit(
            id=f"u-{i}",
            property_id="prop-1",
            unit_number=str(100 + i),
            status=UnitStatus.OCCUPIED,
            days_vacant=5,
        ))
    await property_store.upsert_unit(Unit(
        id="u-extreme",
        property_id="prop-1",
        unit_number="999",
        status=UnitStatus.VACANT,
        days_vacant=300,
    ))

    detector = PatternDetector(
        ontology_store, hypothesis_store,
        zscore_threshold=2.0, min_sample_size=5,
    )
    detect_result = await detector.run()
    assert detect_result.proposed >= 1

    proposed = await hypothesis_store.list_hypotheses(status="proposed")
    assert len(proposed) >= 1

    for hyp in proposed:
        await hypothesis_store.update_status(
            hyp.hypothesis_id, HypothesisStatus.CONFIRMED,
            reviewed_by="test_suite",
        )

    initial_signals = len(mutable_domain.all_signal_names())

    graduator = HypothesisGraduator(
        mutable_domain, ontology_store, hypothesis_store,
    )
    grad_results = await graduator.graduate_all_confirmed()
    graduated = [r for r in grad_results if r.graduated]
    assert len(graduated) >= 1

    signal_defs_created = [
        r for r in graduated
        if any(e.get("type") == "signal_definition" for e in r.tbox_entries_created)
    ]
    if signal_defs_created:
        assert len(mutable_domain.all_signal_names()) > initial_signals


# -- Helpers ------------------------------------------------------------------


async def _bootstrap(ontology_store: BridgedOntologyStore) -> None:
    from remi.infrastructure.ontology.bootstrap import bootstrap_ontology

    await bootstrap_ontology(ontology_store)
