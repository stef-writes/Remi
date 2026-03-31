"""Backward-compat shim — import from knowledge.ontology.remote instead."""

from remi.knowledge.ontology.remote import RemoteKnowledgeGraph, RemoteOntologyStore

__all__ = ["RemoteKnowledgeGraph", "RemoteOntologyStore"]
