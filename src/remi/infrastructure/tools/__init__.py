"""Incline: Tool implementations — ontology, documents, memory, sandbox, trace, vectors."""

from __future__ import annotations

from typing import Any

from remi.domain.documents.models import DocumentStore
from remi.domain.memory.ports import MemoryStore
from remi.domain.ontology.ports import OntologyStore
from remi.domain.retrieval.ports import Embedder, VectorStore
from remi.domain.sandbox.ports import Sandbox
from remi.domain.signals.ports import SignalStore
from remi.domain.trace.ports import TraceStore
from remi.domain.tools.ports import ToolRegistry

from remi.infrastructure.tools.documents import register_document_tools
from remi.infrastructure.tools.memory import register_memory_tools
from remi.infrastructure.tools.ontology import register_ontology_tools
from remi.infrastructure.tools.sandbox import register_sandbox_tools
from remi.infrastructure.tools.trace import register_trace_tools
from remi.infrastructure.tools.vectors import register_vector_tools


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

    register_ontology_tools(registry, ontology_store=ontology_store,
                            signal_store=signal_store)
    register_document_tools(registry, document_store=document_store)
    register_memory_tools(registry, memory_store=memory_store)
    register_trace_tools(registry, trace_store=trace_store)
    register_sandbox_tools(registry, sandbox=sandbox)
    if vector_store is not None and embedder is not None:
        register_vector_tools(registry, vector_store=vector_store, embedder=embedder)
