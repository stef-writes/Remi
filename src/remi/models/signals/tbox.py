"""TBox models — declarative domain expertise as typed, frozen structures."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from remi.models.signals.enums import Deontic, Horizon, RuleCondition, Severity


class InferenceRule(BaseModel, frozen=True):
    """A declarative rule the entailment engine evaluates.

    The engine dispatches on ``condition``. Each condition type knows
    which fields it needs (threshold_key, window_key, periods, etc.).
    """

    metric: str
    condition: RuleCondition
    threshold_key: str | None = None
    window_key: str | None = None
    periods: int | None = None
    percentile: int | None = None
    statuses: list[str] | None = None


class SignalDefinition(BaseModel, frozen=True):
    """A named domain concept the entailment engine can detect.

    This is the TBox entry for a signal — what it means, when it fires,
    and how to evaluate it. The engine reads this; no Python method per signal.

    ``entity`` is a plain string so any domain can define its own entity
    types. REMI uses EntityType enum values; a health domain could pass
    "Patient", "Encounter", etc.
    """

    name: str
    description: str
    severity: Severity
    entity: str
    horizon: Horizon
    rule: InferenceRule
    related_policies: list[str] = Field(default_factory=list)
    caused_by: list[str] = Field(default_factory=list)


class Policy(BaseModel, frozen=True):
    """A deontic obligation — something that MUST or SHOULD happen."""

    id: str
    description: str
    trigger: str
    deontic: Deontic


class CausalChain(BaseModel, frozen=True):
    """A known cause-effect relationship in the domain."""

    cause: str
    effect: str
    description: str


class WorkflowStep(BaseModel, frozen=True):
    id: str
    description: str


class WorkflowSeed(BaseModel, frozen=True):
    name: str
    steps: list[WorkflowStep]


class DomainOntology(BaseModel, frozen=True):
    """The full TBox + ABox seeds, parsed from domain.yaml.

    Every field is typed. Every query method returns typed models.
    Adding a signal to domain.yaml and having it fail Pydantic validation
    is the correct outcome — it means the YAML is wrong, not the code.
    """

    signals: dict[str, SignalDefinition] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)
    policies: list[Policy] = Field(default_factory=list)
    causal_chains: list[CausalChain] = Field(default_factory=list)
    workflows: list[WorkflowSeed] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, raw: dict[str, Any]) -> DomainOntology:
        tbox = raw.get("tbox", {})
        abox = raw.get("abox", {})

        raw_signals = tbox.get("signals", [])
        signal_defs: dict[str, SignalDefinition] = {}
        for s in raw_signals:
            defn = SignalDefinition(
                name=s["name"],
                description=s.get("description", "").strip(),
                severity=Severity(s["severity"]),
                entity=s["entity"],
                horizon=Horizon(s["horizon"]),
                rule=InferenceRule(**s["rule"]),
            )
            signal_defs[defn.name] = defn

        policies = [
            Policy(
                id=p["id"],
                description=p.get("description", ""),
                trigger=p.get("trigger", ""),
                deontic=Deontic(p["deontic"]),
            )
            for p in tbox.get("policies", [])
        ]

        causal_chains = [
            CausalChain(
                cause=c["cause"],
                effect=c["effect"],
                description=c.get("description", ""),
            )
            for c in tbox.get("causal_chains", [])
        ]

        workflows = [
            WorkflowSeed(
                name=w["name"],
                steps=[WorkflowStep(**step) for step in w.get("steps", [])],
            )
            for w in abox.get("workflows", [])
        ]

        return cls(
            signals=signal_defs,
            thresholds=tbox.get("thresholds", {}),
            policies=policies,
            causal_chains=causal_chains,
            workflows=workflows,
        )

    def threshold(self, key: str, default: float = 0.0) -> float:
        return self.thresholds.get(key, default)

    def signals_for_entity(self, entity: str) -> list[SignalDefinition]:
        return [d for d in self.signals.values() if d.entity == entity]

    def signal(self, name: str) -> SignalDefinition | None:
        return self.signals.get(name)

    def policies_for_trigger(self, trigger: str) -> list[Policy]:
        return [p for p in self.policies if p.trigger == trigger]

    def policies_for_signal(self, signal_name: str) -> list[Policy]:
        name_lower = signal_name.lower()
        return [p for p in self.policies if name_lower in p.trigger.lower()]

    def causal_parents(self, effect: str) -> list[CausalChain]:
        return [c for c in self.causal_chains if c.effect == effect]

    def causal_children(self, cause: str) -> list[CausalChain]:
        return [c for c in self.causal_chains if c.cause == cause]

    def all_signal_names(self) -> list[str]:
        return list(self.signals.keys())


class MutableDomainOntology:
    """Runtime-writable view over a frozen DomainOntology.

    The static DomainOntology (from domain.yaml) is immutable. This wrapper
    adds a mutable layer for hypotheses that have been confirmed and graduated
    into the TBox.
    """

    def __init__(self, base: DomainOntology) -> None:
        self._base = base
        self._extra_signals: dict[str, SignalDefinition] = {}
        self._extra_thresholds: dict[str, float] = {}
        self._extra_chains: list[CausalChain] = []

    @property
    def base(self) -> DomainOntology:
        return self._base

    @property
    def signals(self) -> dict[str, SignalDefinition]:
        merged = dict(self._base.signals)
        merged.update(self._extra_signals)
        return merged

    @property
    def thresholds(self) -> dict[str, float]:
        merged = dict(self._base.thresholds)
        merged.update(self._extra_thresholds)
        return merged

    @property
    def causal_chains(self) -> list[CausalChain]:
        return list(self._base.causal_chains) + list(self._extra_chains)

    @property
    def policies(self) -> list[Policy]:
        return list(self._base.policies)

    @property
    def workflows(self) -> list[WorkflowSeed]:
        return list(self._base.workflows)

    def threshold(self, key: str, default: float = 0.0) -> float:
        if key in self._extra_thresholds:
            return self._extra_thresholds[key]
        return self._base.threshold(key, default)

    def signals_for_entity(self, entity: str) -> list[SignalDefinition]:
        base = self._base.signals_for_entity(entity)
        extra = [d for d in self._extra_signals.values() if d.entity == entity]
        return base + extra

    def signal(self, name: str) -> SignalDefinition | None:
        if name in self._extra_signals:
            return self._extra_signals[name]
        return self._base.signal(name)

    def policies_for_trigger(self, trigger: str) -> list[Policy]:
        return self._base.policies_for_trigger(trigger)

    def policies_for_signal(self, signal_name: str) -> list[Policy]:
        return self._base.policies_for_signal(signal_name)

    def causal_parents(self, effect: str) -> list[CausalChain]:
        base = self._base.causal_parents(effect)
        extra = [c for c in self._extra_chains if c.effect == effect]
        return base + extra

    def causal_children(self, cause: str) -> list[CausalChain]:
        base = self._base.causal_children(cause)
        extra = [c for c in self._extra_chains if c.cause == cause]
        return base + extra

    def all_signal_names(self) -> list[str]:
        return list(self.signals.keys())

    def add_signal(self, defn: SignalDefinition) -> None:
        self._extra_signals[defn.name] = defn

    def set_threshold(self, key: str, value: float) -> None:
        self._extra_thresholds[key] = value

    def add_causal_chain(self, chain: CausalChain) -> None:
        self._extra_chains.append(chain)

    @property
    def learned_signal_count(self) -> int:
        return len(self._extra_signals)

    @property
    def learned_chain_count(self) -> int:
        return len(self._extra_chains)
