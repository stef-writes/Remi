"""Factory: assembles the full RE signal pipeline.

Wires EntailmentEngine + StatisticalProducer + CompositionProducer into a
CompositeProducer. RE-specific — lives in ``monitoring/signals/``.
"""

from __future__ import annotations

from remi.agent.graph.stores import KnowledgeGraph
from remi.agent.observe.types import Tracer
from remi.agent.signals import MutableTBox, SignalStore
from remi.agent.signals.producers.composite import CompositeProducer
from remi.agent.signals.producers.composition import CompositionProducer
from remi.agent.signals.producers.statistical import StatisticalProducer
from remi.application.core.protocols import PropertyStore
from remi.application.services.monitoring.signals.engine import EntailmentEngine
from remi.application.services.monitoring.snapshots.service import SnapshotService


def build_signal_pipeline(
    *,
    domain: MutableTBox,
    property_store: PropertyStore,
    signal_store: SignalStore,
    snapshot_service: SnapshotService,
    knowledge_graph: KnowledgeGraph,
    tracer: Tracer,
) -> CompositeProducer:
    """Factory: assembles the full signal pipeline (entailment + statistical + composition)."""
    entailment_engine = EntailmentEngine(
        domain=domain,
        property_store=property_store,
        signal_store=signal_store,
        tracer=tracer,
        snapshot_service=snapshot_service,
    )
    return CompositeProducer(
        signal_store=signal_store,
        producers=[
            entailment_engine,
            StatisticalProducer(knowledge_graph=knowledge_graph),
            CompositionProducer(domain=domain, signal_store=signal_store),
        ],
        tracer=tracer,
    )
