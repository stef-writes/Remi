"""TBox models — declarative domain expertise as typed, frozen structures.

DomainTBox holds signal definitions, thresholds, policies, causal chains,
composition rules, and workflows parsed from domain.yaml. MutableTBox is
a thin forwarding wrapper providing the same read interface.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from remi.agent.signals.enums import Deontic, Horizon, RuleCondition, Severity


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


class CompositionRule(BaseModel, frozen=True):
    """When multiple signals co-occur on the same entity, emit a composite signal.

    Constituents are signal type names. The engine checks that all are
    active on a single entity of the given ``scope`` type before firing.
    """

    name: str
    description: str
    constituents: list[str]
    scope: str
    severity: Severity
    require_same_entity: bool = True


class WorkflowStep(BaseModel, frozen=True):
    id: str
    description: str


class WorkflowSeed(BaseModel, frozen=True):
    name: str
    steps: list[WorkflowStep]


class DomainTBox(BaseModel, frozen=True):
    """Declarative business rules and calibrations, parsed from domain.yaml.

    Every field is typed. Every query method returns typed models.
    Adding a signal to domain.yaml and having it fail Pydantic validation
    is the correct outcome — it means the YAML is wrong, not the code.
    """

    signals: dict[str, SignalDefinition] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)
    policies: list[Policy] = Field(default_factory=list)
    causal_chains: list[CausalChain] = Field(default_factory=list)
    compositions: list[CompositionRule] = Field(default_factory=list)
    workflows: list[WorkflowSeed] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, raw: dict[str, Any]) -> DomainTBox:
        tbox = raw.get("tbox", {})
        abox = raw.get("abox", {})

        raw_signals: list[dict[str, Any]] = []
        raw_policies: list[dict[str, Any]] = []
        raw_thresholds: dict[str, float] = {}
        raw_chains: list[dict[str, Any]] = []

        _TOP_LEVEL_KEYS = {
            "compositions", "signals", "policies",
            "thresholds", "causal_chains",
        }

        for key, section in tbox.items():
            if key in _TOP_LEVEL_KEYS or not isinstance(section, dict):
                continue
            raw_signals.extend(section.get("signals", []))
            raw_policies.extend(section.get("policies", []))
            raw_thresholds.update(section.get("thresholds", {}))
            raw_chains.extend(section.get("causal_chains", []))

        raw_signals.extend(tbox.get("signals", []))
        raw_policies.extend(tbox.get("policies", []))
        raw_thresholds.update(tbox.get("thresholds", {}))
        raw_chains.extend(tbox.get("causal_chains", []))

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
            for p in raw_policies
        ]

        causal_chains = [
            CausalChain(
                cause=c["cause"],
                effect=c["effect"],
                description=c.get("description", ""),
            )
            for c in raw_chains
        ]

        compositions = [
            CompositionRule(
                name=c["name"],
                description=c.get("description", "").strip(),
                constituents=c["constituents"],
                scope=c["scope"],
                severity=Severity(c["severity"]),
                require_same_entity=c.get("require_same_entity", True),
            )
            for c in tbox.get("compositions", [])
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
            thresholds=raw_thresholds,
            policies=policies,
            causal_chains=causal_chains,
            compositions=compositions,
            workflows=workflows,
        )

    def threshold(self, key: str, default: float = 0.0) -> float:
        return self.thresholds.get(key, default)

    def signals_for_entity(self, entity: str) -> list[SignalDefinition]:
        return [d for d in self.signals.values() if d.entity == entity]

    def signal(self, name: str) -> SignalDefinition | None:
        return self.signals.get(name)

    def all_signal_names(self) -> list[str]:
        names = list(self.signals.keys())
        names.extend(c.name for c in self.compositions)
        return names



class MutableTBox:
    """Thin forwarding wrapper over a frozen DomainTBox.

    Provides the same read interface as DomainTBox so that callers
    can accept ``DomainTBox | MutableTBox`` without branching.
    """

    def __init__(self, base: DomainTBox) -> None:
        self._base = base

    @property
    def base(self) -> DomainTBox:
        return self._base

    @property
    def signals(self) -> dict[str, SignalDefinition]:
        return dict(self._base.signals)

    @property
    def thresholds(self) -> dict[str, float]:
        return dict(self._base.thresholds)

    @property
    def causal_chains(self) -> list[CausalChain]:
        return list(self._base.causal_chains)

    @property
    def policies(self) -> list[Policy]:
        return list(self._base.policies)

    @property
    def compositions(self) -> list[CompositionRule]:
        return list(self._base.compositions)

    @property
    def workflows(self) -> list[WorkflowSeed]:
        return list(self._base.workflows)

    def threshold(self, key: str, default: float = 0.0) -> float:
        return self._base.threshold(key, default)

    def signals_for_entity(self, entity: str) -> list[SignalDefinition]:
        return self._base.signals_for_entity(entity)

    def signal(self, name: str) -> SignalDefinition | None:
        return self._base.signal(name)

    def all_signal_names(self) -> list[str]:
        return self._base.all_signal_names()

