"""Test that domain.yaml loads and parses into fully typed TBox models."""

from __future__ import annotations

from remi.domain.signals.types import (
    CausalChain,
    Deontic,
    DomainOntology,
    EntityType,
    Horizon,
    InferenceRule,
    Policy,
    RuleCondition,
    Severity,
    SignalDefinition,
)
from remi.infrastructure.ontology.bootstrap import load_domain_yaml


EXPECTED_SIGNAL_NAMES = {
    "OccupancyDrift",
    "DelinquencyConcentration",
    "LeaseExpirationCliff",
    "VacancyDuration",
    "MaintenanceBacklog",
    "OutlierPerformance",
    "PerformanceTrend",
    "CommunicationGap",
    "PolicyBreach",
    "LegalEscalationRisk",
    "BelowMarketRent",
    "ConcentrationRisk",
}


def _domain() -> DomainOntology:
    return DomainOntology.from_yaml(load_domain_yaml())


class TestYamlLoading:
    def test_domain_yaml_loads(self) -> None:
        raw = load_domain_yaml()
        assert raw["apiVersion"] == "remi/v1"
        assert raw["kind"] == "DomainOntology"

    def test_domain_ontology_parses_typed(self) -> None:
        domain = _domain()
        assert len(domain.signals) == 12
        assert len(domain.thresholds) > 0
        assert len(domain.policies) > 0
        assert len(domain.causal_chains) > 0
        assert len(domain.workflows) == 3

    def test_all_twelve_signal_types_defined(self) -> None:
        domain = _domain()
        assert set(domain.signals.keys()) == EXPECTED_SIGNAL_NAMES


class TestTypedSignalDefinitions:
    def test_signal_definitions_are_typed(self) -> None:
        domain = _domain()
        for name, defn in domain.signals.items():
            assert isinstance(defn, SignalDefinition), f"{name} should be SignalDefinition"
            assert isinstance(defn.severity, Severity), f"{name}.severity should be Severity enum"
            assert isinstance(defn.entity, str), f"{name}.entity should be a string"
            assert defn.entity, f"{name}.entity should be non-empty"
            assert isinstance(defn.horizon, Horizon), f"{name}.horizon should be Horizon enum"
            assert isinstance(defn.rule, InferenceRule), f"{name}.rule should be InferenceRule"
            assert isinstance(defn.rule.condition, RuleCondition), f"{name}.rule.condition should be RuleCondition"

    def test_vacancy_duration_definition(self) -> None:
        defn = _domain().signal("VacancyDuration")
        assert defn is not None
        assert defn.severity == Severity.MEDIUM
        assert defn.entity == EntityType.UNIT
        assert defn.rule.condition == RuleCondition.EXCEEDS_THRESHOLD
        assert defn.rule.threshold_key == "vacancy_chronic_days"
        assert defn.rule.metric == "days_vacant"

    def test_legal_escalation_definition(self) -> None:
        defn = _domain().signal("LegalEscalationRisk")
        assert defn is not None
        assert defn.severity == Severity.HIGH
        assert defn.entity == EntityType.TENANT
        assert defn.rule.condition == RuleCondition.IN_LEGAL_TRACK
        assert defn.rule.statuses == ["evict"]


class TestTypedPolicies:
    def test_policies_are_typed(self) -> None:
        domain = _domain()
        for pol in domain.policies:
            assert isinstance(pol, Policy)
            assert isinstance(pol.deontic, Deontic)
            assert pol.id.startswith("policy:")

    def test_all_policies_are_must_or_should(self) -> None:
        domain = _domain()
        for pol in domain.policies:
            assert pol.deontic in (Deontic.MUST, Deontic.SHOULD)


class TestTypedCausalChains:
    def test_causal_chains_are_typed(self) -> None:
        domain = _domain()
        for chain in domain.causal_chains:
            assert isinstance(chain, CausalChain)
            assert chain.cause
            assert chain.effect
            assert chain.description


class TestThresholds:
    def test_thresholds_have_expected_keys(self) -> None:
        domain = _domain()
        for key in ("vacancy_chronic_days", "lease_cliff_pct", "delinquency_critical_pct",
                     "maintenance_backlog_days", "below_market_rent_pct"):
            assert key in domain.thresholds, f"Missing threshold: {key}"
            assert domain.threshold(key) > 0


class TestDomainQueries:
    """The TBox is queryable — not just a bag, but a navigable structure."""

    def test_signals_for_entity_unit(self) -> None:
        domain = _domain()
        unit_signals = domain.signals_for_entity(EntityType.UNIT)
        names = {d.name for d in unit_signals}
        assert "VacancyDuration" in names
        assert "BelowMarketRent" in names
        assert "DelinquencyConcentration" not in names

    def test_signals_for_entity_manager(self) -> None:
        domain = _domain()
        mgr_signals = domain.signals_for_entity(EntityType.PROPERTY_MANAGER)
        names = {d.name for d in mgr_signals}
        assert "DelinquencyConcentration" in names
        assert "LeaseExpirationCliff" in names
        assert "MaintenanceBacklog" in names

    def test_signal_lookup_by_name(self) -> None:
        domain = _domain()
        assert domain.signal("VacancyDuration") is not None
        assert domain.signal("NonexistentSignal") is None

    def test_causal_parents(self) -> None:
        domain = _domain()
        parents = domain.causal_parents("extended_vacancy")
        assert len(parents) >= 1
        assert any(c.cause == "slow_maintenance" for c in parents)

    def test_causal_children(self) -> None:
        domain = _domain()
        children = domain.causal_children("below_market_rent")
        assert len(children) >= 1
        assert any(c.effect == "missed_revenue" for c in children)

    def test_all_signal_names(self) -> None:
        domain = _domain()
        names = domain.all_signal_names()
        assert len(names) == 12
        assert "VacancyDuration" in names
