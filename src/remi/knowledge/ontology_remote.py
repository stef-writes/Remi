"""Backward-compat shim — import from knowledge.ontology.remote instead."""

from remi.knowledge.ontology.remote import RemoteOntologyStore

__all__ = ["RemoteOntologyStore"]
