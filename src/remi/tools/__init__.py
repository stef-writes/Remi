"""Incline: Tool implementations — ontology, documents, memory, sandbox, trace, vectors."""

from __future__ import annotations

from remi.models.documents import DocumentStore
from remi.models.memory import MemoryStore
from remi.models.ontology import OntologyStore
from remi.models.retrieval import Embedder, VectorStore
from remi.models.sandbox import Sandbox
from remi.models.signals import SignalStore
from remi.models.tools import ToolRegistry
from remi.models.trace import TraceStore
from remi.tools.documents import register_document_tools
from remi.tools.memory import register_memory_tools
from remi.tools.ontology import register_ontology_tools
from remi.tools.sandbox import register_sandbox_tools
from remi.tools.trace import register_trace_tools
from remi.tools.vectors import register_vector_tools


def register_all_tools(
    registry: ToolRegistry,
    *,
    ontology_store: OntologyStore,
    document_store: DocumentStore,
    memory_store: MemoryStore | None = None,
    signal_store: SignalStore | None = None,
    vector_store: VectorStore | None = None,
    embedder: Embedder | None = None,
    trace_store: TraceStore | None = None,
    sandbox: Sandbox | None = None,
) -> None:
    """Register every tool group into *registry* using shared in-process stores."""

    register_ontology_tools(registry, ontology_store=ontology_store, signal_store=signal_store)
    register_document_tools(registry, document_store=document_store)
    register_memory_tools(registry, memory_store=memory_store)
    register_trace_tools(registry, trace_store=trace_store)
    register_sandbox_tools(registry, sandbox=sandbox)
    if vector_store is not None and embedder is not None:
        register_vector_tools(registry, vector_store=vector_store, embedder=embedder)
