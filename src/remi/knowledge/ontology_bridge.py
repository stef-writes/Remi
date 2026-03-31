"""Backward-compat shim — import from knowledge.ontology.bridge instead."""

from remi.knowledge.ontology.bridge import (
    BridgedKnowledgeGraph,
    BridgedOntologyStore,
    CoreTypeBindings,
)

__all__ = ["BridgedKnowledgeGraph", "BridgedOntologyStore", "CoreTypeBindings"]
