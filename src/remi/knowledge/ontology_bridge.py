"""Backward-compat shim — import from knowledge.ontology.bridge instead."""

from remi.knowledge.ontology.bridge import BridgedOntologyStore, CoreTypeBindings

__all__ = ["BridgedOntologyStore", "CoreTypeBindings"]
