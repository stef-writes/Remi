"""Backward-compat shim — import from knowledge.ontology.bootstrap instead."""

from remi.knowledge.ontology.bootstrap import (
    bootstrap_knowledge_graph,
    bootstrap_ontology,
    load_domain_yaml,
)

__all__ = ["bootstrap_knowledge_graph", "bootstrap_ontology", "load_domain_yaml"]
