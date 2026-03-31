"""Backward-compat shim — import from knowledge.ontology.bootstrap instead."""

from remi.knowledge.ontology.bootstrap import bootstrap_ontology, load_domain_yaml

__all__ = ["bootstrap_ontology", "load_domain_yaml"]
