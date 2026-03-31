"""knowledge.ontology — OntologyStore implementations and bootstrap.

Subpackage containing:
  bridge    — BridgedOntologyStore (local in-process, backed by PropertyStore + KnowledgeStore)
  remote    — RemoteOntologyStore (HTTP client, used by sandbox processes)
  bootstrap — domain.yaml loader and one-time ontology bootstrapping
"""

from remi.knowledge.ontology.bootstrap import bootstrap_ontology, load_domain_yaml
from remi.knowledge.ontology.bridge import BridgedOntologyStore, CoreTypeBindings
from remi.knowledge.ontology.remote import RemoteOntologyStore

__all__ = [
    "BridgedOntologyStore",
    "CoreTypeBindings",
    "RemoteOntologyStore",
    "bootstrap_ontology",
    "load_domain_yaml",
]
