"""Domain expertise as first-class typed models.

Every concept in the TBox — signal definitions, inference rules, policies,
causal chains — is a frozen Pydantic model with validated fields. The
DomainOntology is queryable at runtime: ask it for signals by entity type,
policies by trigger, causal parents of a signal, etc.

The EntailmentEngine dispatches on RuleCondition, not on method names.
Adding a new signal to domain.yaml is sufficient — no new Python code required
for conditions the engine already understands.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Enums — closed vocabularies for the domain
# ---------------------------------------------------------------------------


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EntityType(StrEnum):
    """Well-known entity types for the REMI real-estate product.

    This enum is REMI-specific, not part of Incline's framework contract.
    Framework code (SignalDefinition, Signal, etc.) uses plain ``str`` for
    entity types so any domain can pass its own values.

    Kept here for backward compatibility; canonical home is
    ``remi.domain.properties.entity_types``.
    """

    PROPERTY_MANAGER = "PropertyManager"
    PROPERTY = "Property"
    PORTFOLIO = "Portfolio"
    UNIT = "Unit"
    TENANT = "Tenant"
    LEASE = "Lease"
    MAINTENANCE_REQUEST = "MaintenanceRequest"


class Horizon(StrEnum):
    CURRENT = "current"
    CURRENT_PERIOD = "current_period"
    TRAILING_60_DAYS = "trailing_60_days"
    TRAILING_90_DAYS = "trailing_90_days"
    NEXT_60_DAYS = "next_60_days"
    EVENT_DRIVEN = "event_driven"


class RuleCondition(StrEnum):
    """The finite set of evaluation strategies the engine understands."""
    EXCEEDS_THRESHOLD = "exceeds_threshold"
    AGING_PAST_THRESHOLD = "aging_past_threshold"
    DECLINING_CONSECUTIVE_PERIODS = "declining_consecutive_periods"
    BELOW_PERCENTILE = "below_percentile"
    CONSISTENT_DIRECTION = "consistent_direction"
    IN_LEGAL_TRACK = "in_legal_track"
    EXISTS = "exists"
    BREACH_DETECTED = "breach_detected"


class Deontic(StrEnum):
    MUST = "MUST"
    SHOULD = "SHOULD"


class Provenance(StrEnum):
    CORE = "CORE"
    SEEDED = "SEEDED"
    DATA_DERIVED = "DATA_DERIVED"
    USER_STATED = "USER_STATED"
    INFERRED = "INFERRED"


# ---------------------------------------------------------------------------
# TBox models — domain expertise as typed, frozen structures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Signal — the runtime entailed state (produced by the engine)
# ---------------------------------------------------------------------------


class Signal(BaseModel, frozen=True):
    """A named, evidenced, severity-ranked entailed state.

    Produced by a SignalProducer (rule engine, statistical detector, or
    learned model) when its evaluation criteria are met against ABox facts.

    ``entity_type`` accepts any string — EntityType enum values for RE,
    arbitrary strings for custom domains.
    """

    signal_id: str
    signal_type: str
    severity: Severity
    entity_type: str
    entity_id: str
    entity_name: str = ""
    description: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime = Field(default_factory=_utcnow)
    provenance: Provenance = Provenance.DATA_DERIVED


# ---------------------------------------------------------------------------
# DomainOntology — the TBox as a queryable, typed structure
# ---------------------------------------------------------------------------


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

    # -- Constructors -------------------------------------------------------

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

    # -- Threshold access ---------------------------------------------------

    def threshold(self, key: str, default: float = 0.0) -> float:
        return self.thresholds.get(key, default)

    # -- Typed queries — domain expertise is programmatically navigable -----

    def signals_for_entity(self, entity: str) -> list[SignalDefinition]:
        """All signal definitions that apply to a given entity type."""
        return [d for d in self.signals.values() if d.entity == entity]

    def signal(self, name: str) -> SignalDefinition | None:
        """Look up a single signal definition by name."""
        return self.signals.get(name)

    def policies_for_trigger(self, trigger: str) -> list[Policy]:
        """Policies activated by a given trigger condition."""
        return [p for p in self.policies if p.trigger == trigger]

    def policies_for_signal(self, signal_name: str) -> list[Policy]:
        """Policies related to a signal (by convention: trigger contains signal name)."""
        name_lower = signal_name.lower()
        return [p for p in self.policies if name_lower in p.trigger.lower()]

    def causal_parents(self, effect: str) -> list[CausalChain]:
        """What causes a given effect?"""
        return [c for c in self.causal_chains if c.effect == effect]

    def causal_children(self, cause: str) -> list[CausalChain]:
        """What does a given cause lead to?"""
        return [c for c in self.causal_chains if c.cause == cause]

    def all_signal_names(self) -> list[str]:
        return list(self.signals.keys())
