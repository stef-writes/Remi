"""models.signals — signal system models.

Submodules:
  enums      — Severity, RuleCondition, Horizon, Deontic, SignalOutcome, etc.
  tbox       — SignalDefinition, Policy, CausalChain, DomainOntology, MutableDomainOntology
  signal     — Signal, ProducerResult, SignalProducer
  feedback   — SignalFeedback, SignalFeedbackSummary
  hypothesis — Hypothesis, HypothesisKind/Status
  stores     — SignalStore, FeedbackStore, HypothesisStore ABCs

All symbols are re-exported here for backward compatibility — existing
``from remi.models.signals import Foo`` imports continue to work unchanged.
"""

from remi.models.ontology import KnowledgeProvenance as Provenance
from remi.models.signals.enums import (
    Deontic,
    EntityType,
    Horizon,
    HypothesisKind,
    HypothesisStatus,
    RuleCondition,
    Severity,
    SignalOutcome,
)
from remi.models.signals.feedback import SignalFeedback, SignalFeedbackSummary
from remi.models.signals.hypothesis import Hypothesis
from remi.models.signals.signal import ProducerResult, Signal, SignalProducer
from remi.models.signals.stores import FeedbackStore, HypothesisStore, SignalStore
from remi.models.signals.tbox import (
    CausalChain,
    DomainOntology,
    InferenceRule,
    MutableDomainOntology,
    Policy,
    SignalDefinition,
    WorkflowSeed,
    WorkflowStep,
)

__all__ = [
    # enums
    "Deontic",
    "EntityType",
    "Horizon",
    "HypothesisKind",
    "HypothesisStatus",
    "Provenance",
    "RuleCondition",
    "Severity",
    "SignalOutcome",
    # tbox
    "CausalChain",
    "DomainOntology",
    "InferenceRule",
    "MutableDomainOntology",
    "Policy",
    "SignalDefinition",
    "WorkflowSeed",
    "WorkflowStep",
    # signal
    "ProducerResult",
    "Signal",
    "SignalProducer",
    # feedback
    "SignalFeedback",
    "SignalFeedbackSummary",
    # hypothesis
    "Hypothesis",
    # stores
    "FeedbackStore",
    "HypothesisStore",
    "SignalStore",
]
