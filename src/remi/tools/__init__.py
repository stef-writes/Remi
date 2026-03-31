"""Incline: Tool implementations — ontology, documents, memory, sandbox, trace, vectors, actions, workflows."""

from __future__ import annotations

from remi.models.documents import DocumentStore
from remi.models.memory import MemoryStore
from remi.models.ontology import KnowledgeGraph
from remi.models.properties import PropertyStore
from remi.models.retrieval import Embedder, VectorStore
from remi.models.sandbox import Sandbox
from remi.models.signals import SignalStore
from remi.models.tools import ToolRegistry
from remi.models.trace import TraceStore
from remi.services.dashboard import DashboardQueryService
from remi.services.manager_review import ManagerReviewService
from remi.tools.actions import register_action_tools
from remi.tools.documents import register_document_tools
from remi.tools.memory import register_memory_tools
from remi.tools.ontology import register_knowledge_graph_tools
from remi.tools.sandbox import register_sandbox_tools
from remi.tools.trace import register_trace_tools
from remi.tools.vectors import register_vector_tools
from remi.tools.workflows import SubAgentInvoker, register_workflow_tools


def register_all_tools(
    registry: ToolRegistry,
    *,
    knowledge_graph: KnowledgeGraph,
    document_store: DocumentStore,
    property_store: PropertyStore | None = None,
    memory_store: MemoryStore | None = None,
    signal_store: SignalStore | None = None,
    vector_store: VectorStore | None = None,
    embedder: Embedder | None = None,
    trace_store: TraceStore | None = None,
    sandbox: Sandbox | None = None,
    manager_review: ManagerReviewService | None = None,
    dashboard_service: DashboardQueryService | None = None,
    sub_agent: SubAgentInvoker | None = None,
) -> None:
    """Register every tool group into *registry* using shared in-process stores."""

    register_knowledge_graph_tools(
        registry, knowledge_graph=knowledge_graph, signal_store=signal_store
    )
    register_document_tools(registry, document_store=document_store)
    register_memory_tools(registry, memory_store=memory_store)
    register_trace_tools(registry, trace_store=trace_store)
    register_sandbox_tools(registry, sandbox=sandbox)
    if vector_store is not None and embedder is not None:
        register_vector_tools(registry, vector_store=vector_store, embedder=embedder)
    if property_store is not None:
        register_action_tools(
            registry,
            property_store=property_store,
            knowledge_graph=knowledge_graph,
        )
    if (
        property_store is not None
        and manager_review is not None
        and dashboard_service is not None
    ):
        register_workflow_tools(
            registry,
            property_store=property_store,
            knowledge_graph=knowledge_graph,
            manager_review=manager_review,
            dashboard_service=dashboard_service,
            sub_agent=sub_agent,
        )
