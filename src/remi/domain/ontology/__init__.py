"""Incline: Ontology system — schema, queries, and knowledge codification ports."""

from remi.domain.ontology.ports import OntologyStore
from remi.domain.ontology.types import (
    ActionDef,
    KnowledgeProvenance,
    LinkTypeDef,
    ObjectTypeDef,
    PropertyDef,
)

__all__ = [
    "ActionDef",
    "KnowledgeProvenance",
    "LinkTypeDef",
    "ObjectTypeDef",
    "OntologyStore",
    "PropertyDef",
]
