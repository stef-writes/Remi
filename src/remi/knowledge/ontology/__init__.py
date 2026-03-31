"""knowledge.ontology — KnowledgeGraph implementations and bootstrap.

Subpackage containing:
  bridge    — BridgedKnowledgeGraph (local in-process, backed by PropertyStore + KnowledgeStore)
  remote    — RemoteKnowledgeGraph (HTTP client, used by sandbox processes)
  bootstrap — domain.yaml loader and one-time knowledge graph bootstrapping
"""

from remi.knowledge.ontology.bootstrap import (
    bootstrap_knowledge_graph,
    bootstrap_ontology,
    load_domain_yaml,
)
from remi.knowledge.ontology.bridge import (
    BridgedKnowledgeGraph,
    BridgedOntologyStore,
    CoreTypeBindings,
)
from remi.knowledge.ontology.remote import RemoteKnowledgeGraph, RemoteOntologyStore

__all__ = [
    "BridgedKnowledgeGraph",
    "BridgedOntologyStore",
    "CoreTypeBindings",
    "RemoteKnowledgeGraph",
    "RemoteOntologyStore",
    "bootstrap_knowledge_graph",
    "bootstrap_ontology",
    "load_domain_yaml",
]
