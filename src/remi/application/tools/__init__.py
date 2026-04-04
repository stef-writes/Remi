"""tools — RE agent capabilities (conversational agent tools).

Generic capabilities (sandbox, http, memory, vectors, delegation, trace,
registry) live in ``agent/tools/``.  This package holds real-estate-specific
tool registrations and the ``register_all_tools`` aggregator that the
container calls at startup.
"""

from __future__ import annotations

from remi.agent.profile import DomainProfile
from remi.agent.tools.http import register_http_tools
from remi.agent.tools.memory import register_memory_tools
from remi.agent.tools.sandbox import register_sandbox_tools
from remi.agent.tools.trace import register_trace_tools
from remi.agent.tools.vectors import register_vector_tools
from remi.agent.types import ToolArg, ToolRegistry
from remi.agent.documents.types import DocumentStore
from remi.agent.graph.adapters.bridge import BridgedKnowledgeGraph
from remi.agent.graph.stores import MemoryStore
from remi.application.services.ingestion.pipeline import DocumentIngestService
from remi.agent.observe.types import TraceStore
from remi.application.core.protocols import PropertyStore
from remi.agent.sandbox.types import Sandbox
from remi.application.services.search import SearchService
from remi.agent.signals.persistence.stores import SignalStore
from remi.application.tools.actions import register_action_tools
from remi.application.tools.documents import register_document_tools
from remi.application.tools.ontology import register_knowledge_graph_tools
from remi.application.tools.search import register_search_tools
from remi.agent.vectors.types import Embedder, VectorStore


def _build_scope_filter_args(profile: DomainProfile) -> list[ToolArg]:
    """Derive scope filter ToolArgs from the profile's tool_hints."""
    args: list[ToolArg] = []
    if profile.scope_entity_type:
        scope_key = profile.scope_entity_type[0].lower() + profile.scope_entity_type[1:]
        scope_key = scope_key.replace("Manager", "_manager").replace("Property", "_property")
    for key in ("manager_id", "property_id"):
        hint_key = f"semantic_search:{key}"
        desc = profile.tool_hints.get(hint_key, f"Filter results by {key}")
        args.append(ToolArg(name=key, description=desc))
    return args


def register_all_tools(
    registry: ToolRegistry,
    *,
    knowledge_graph: BridgedKnowledgeGraph,
    document_store: DocumentStore,
    property_store: PropertyStore,
    memory_store: MemoryStore,
    signal_store: SignalStore,
    vector_store: VectorStore,
    embedder: Embedder,
    trace_store: TraceStore,
    sandbox: Sandbox,
    search_service: SearchService,
    api_base_url: str,
    profile: DomainProfile | None = None,
    document_ingest: DocumentIngestService | None = None,
) -> None:
    """Phase-1 tool registration (before chat_agent exists).

    Generic capabilities from ``agent/tools/`` plus RE-specific tools
    from ``tools/``.  The *profile* supplies domain-specific description
    hints and scope filter args.
    """
    p = profile or DomainProfile()

    scope_args = _build_scope_filter_args(p) if p.scope_entity_type else []

    register_sandbox_tools(
        registry,
        sandbox=sandbox,
        data_bridge_hint=p.data_bridge_hint,
    )
    register_http_tools(
        registry,
        api_base_url=api_base_url,
        api_path_examples=p.api_path_examples,
    )
    register_memory_tools(registry, memory_store=memory_store)
    register_vector_tools(
        registry,
        vector_store=vector_store,
        embedder=embedder,
        search_hint=p.tool_hints.get("semantic_search", ""),
        entity_type_hint=p.tool_hints.get("semantic_search:entity_type", ""),
        scope_filter_args=scope_args,
    )
    register_trace_tools(registry, trace_store=trace_store)

    # RE-specific
    register_knowledge_graph_tools(
        registry, knowledge_graph=knowledge_graph, signal_store=signal_store
    )
    register_document_tools(
        registry, document_store=document_store, document_ingest=document_ingest
    )
    register_action_tools(
        registry, property_store=property_store, knowledge_graph=knowledge_graph
    )
    register_search_tools(registry, search_service=search_service)
