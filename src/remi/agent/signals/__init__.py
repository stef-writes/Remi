"""signals — signal system: types, stores, producers.

Submodules:
  enums        — Severity, RuleCondition, Horizon, Deontic, SignalOutcome, etc.
  tbox         — SignalDefinition, Policy, CausalChain, DomainTBox, MutableTBox
  signal       — Signal, ProducerResult, SignalProducer
  feedback     — SignalFeedback, SignalFeedbackSummary
  stores       — SignalStore, FeedbackStore ABCs
  evaluation   — MakeSignalFn, EntailmentResult, signal_id (entailment primitives)
  composition  — CompositionProducer (co-occurrence signal producer)
  statistical  — StatisticalProducer (anomaly detection over KG)
  composite    — CompositeProducer (pipeline runner for producers)
"""

from remi.agent.graph.types import KnowledgeProvenance as Provenance
from remi.agent.signals.enums import (
    Deontic,
    Horizon,
    RuleCondition,
    Severity,
    SignalOutcome,
)
from remi.agent.signals.evaluation import EntailmentResult, MakeSignalFn, signal_id
from remi.agent.signals.feedback import SignalFeedback, SignalFeedbackSummary
from remi.agent.signals.signal import ProducerResult, Signal, SignalProducer
from remi.agent.signals.stores import FeedbackStore, SignalStore
from remi.agent.signals.tbox import (
    CausalChain,
    CompositionRule,
    DomainTBox,
    InferenceRule,
    MutableTBox,
    Policy,
    SignalDefinition,
    WorkflowSeed,
    WorkflowStep,
)

__all__ = [
    # enums
    "Deontic",
    "Horizon",
    "Provenance",
    "RuleCondition",
    "Severity",
    "SignalOutcome",
    # tbox
    "CausalChain",
    "CompositionRule",
    "DomainTBox",
    "InferenceRule",
    "MutableTBox",
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
    # evaluation primitives
    "EntailmentResult",
    "MakeSignalFn",
    "signal_id",
    # stores
    "FeedbackStore",
    "SignalStore",
]
