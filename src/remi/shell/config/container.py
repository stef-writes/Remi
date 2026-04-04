"""REMI dependency injection container — pure wiring only.

Calls factory functions from the modules that own the things being built.
No backend selection logic, no LLM adapter registration, no closures.

Only attributes read outside this module are stored as ``self.*``.
Internal intermediaries are local variables.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from remi.agent.context.builder import build_context_builder
from remi.agent.documents.types import DocumentStore
from remi.agent.graph.adapters.bridge import BridgedKnowledgeGraph
from remi.agent.graph.adapters.mem import InMemoryKnowledgeStore, InMemoryMemoryStore
from remi.agent.graph.stores import KnowledgeStore
from remi.agent.ingestion.runner import IngestionPipelineRunner
from remi.agent.llm.factory import LLMProviderFactory, build_provider_factory
from remi.agent.mem import InMemoryChatSessionStore
from remi.agent.observe.mem import InMemoryTraceStore
from remi.agent.observe.types import Tracer, TraceStore
from remi.agent.observe.usage import LLMUsageLedger
from remi.agent.profile import DomainProfile
from remi.agent.runtime.retry import RetryPolicy
from remi.agent.runtime.runner import ChatAgentService
from remi.agent.sandbox.factory import build_sandbox
from remi.agent.sandbox.types import Sandbox
from remi.agent.signals import DomainTBox, FeedbackStore, MutableTBox, SignalStore
from remi.agent.signals.persistence.mem import (
    InMemoryFeedbackStore,
    InMemorySignalStore,
)
from remi.agent.tools.delegation import AgentInvoker, register_delegation_tools
from remi.agent.tools.registry import InMemoryToolRegistry
from remi.agent.types import ChatSessionStore, ToolRegistry
from remi.agent.vectors.embedder import build_embedder
from remi.agent.vectors.store import InMemoryVectorStore
from remi.agent.vectors.types import Embedder, VectorStore
from remi.application.profile import build_re_profile
from remi.application.infra.ontology.bridge import build_knowledge_graph
from remi.application.infra.ontology.schema import load_domain_yaml
from remi.application.infra.ontology.seed import seed_knowledge_graph
from remi.application.core.protocols import PropertyStore
from remi.application.infra.stores.factory import (
    build_document_store,
    build_property_store,
    build_rollup_store,
)
from remi.application.infra.stores.projecting import ProjectingPropertyStore
from remi.application.services.ingestion.pipeline import DocumentIngestService
from remi.application.services.ingestion.service import IngestionService
from remi.application.services.embedding.pipeline import EmbeddingPipeline
from remi.application.services.seeding.cache import StoreBundle
from remi.application.services.seeding.service import SeedService
from remi.application.services.queries.auto_assign import AutoAssignService
from remi.application.services.queries.dashboard import DashboardQueryService
from remi.application.services.queries.managers import ManagerReviewService
from remi.application.services.queries import PortfolioQueryService
from remi.application.services.queries import RentRollService
from remi.application.services.search import SearchService
from remi.application.services.monitoring.signals.pipeline import build_signal_pipeline
from remi.application.core.rollups import RollupStore
from remi.application.services.monitoring.snapshots.service import SnapshotService
from remi.application.tools import register_all_tools
from remi.application.tools.assertions import register_assertion_tools
from remi.application.tools.snapshots import register_snapshot_tools
from remi.application.tools.workflows import SubAgentInvoker, register_workflow_tools
from remi.shell.config.settings import RemiSettings


class Container:
    """REMI container — wires all services for the real estate product."""

    def __init__(self, settings: RemiSettings | None = None) -> None:
        self.settings = settings or RemiSettings()

        # -- Domain profile (operational config for agent layer) ---------------
        self.profile: DomainProfile = build_re_profile()

        # -- Core infrastructure -----------------------------------------------
        memory_store = InMemoryMemoryStore()
        self.knowledge_store: KnowledgeStore = InMemoryKnowledgeStore()
        self.tool_registry: ToolRegistry = InMemoryToolRegistry()
        self.provider_factory: LLMProviderFactory = build_provider_factory(
            self.settings.secrets,
        )

        # -- Stores ------------------------------------------------------------
        self.chat_session_store: ChatSessionStore = InMemoryChatSessionStore()
        self.property_store: PropertyStore
        self._db_engine: AsyncEngine | None
        self._db_session_factory: async_sessionmaker[AsyncSession] | None
        self.property_store, self._db_engine, self._db_session_factory = build_property_store(
            self.settings
        )
        self.document_store: DocumentStore = build_document_store(self._db_session_factory)
        rollup_store = build_rollup_store(self._db_session_factory)

        # -- Knowledge graph ---------------------------------------------------
        from remi.agent.graph.projector import GraphProjector

        self.knowledge_graph: BridgedKnowledgeGraph
        self.graph_projector: GraphProjector
        self.knowledge_graph, self.graph_projector = build_knowledge_graph(
            self.property_store,
            self.knowledge_store,
        )

        # Wrap the store so every upsert auto-projects FK edges into the graph.
        self.property_store = ProjectingPropertyStore(
            self.property_store, self.graph_projector
        )
        self._bootstrap_pending = True

        # -- Trace layer -------------------------------------------------------
        self.trace_store: TraceStore = InMemoryTraceStore()
        self.usage_ledger: LLMUsageLedger = LLMUsageLedger()
        tracer = Tracer(self.trace_store)

        # -- Signal layer ------------------------------------------------------
        raw_domain = load_domain_yaml()
        self.domain_tbox: DomainTBox = DomainTBox.from_yaml(raw_domain)
        mutable_tbox = MutableTBox(self.domain_tbox)
        self.signal_store: SignalStore = InMemorySignalStore()
        self.feedback_store: FeedbackStore = InMemoryFeedbackStore()

        # -- Sandbox -----------------------------------------------------------
        self.sandbox: Sandbox = build_sandbox(self.settings)

        # -- Vectors -----------------------------------------------------------
        self.vector_store: VectorStore = InMemoryVectorStore()
        self.embedder: Embedder = build_embedder(
            self.settings.embeddings,
            self.settings.secrets,
        )

        # -- Adapter registry --------------------------------------------------
        from remi.application.infra.adapters.appfolio.adapter import AppFolioAdapter
        from remi.application.infra.adapters.protocol import AdapterRegistry

        self.adapter_registry = AdapterRegistry()
        self.adapter_registry.register(AppFolioAdapter())

        # -- Services ----------------------------------------------------------
        pipeline_runner = IngestionPipelineRunner(
            provider_factory=self.provider_factory,
            default_provider=self.settings.llm.default_provider,
            default_model=self.settings.llm.default_model,
            usage_ledger=self.usage_ledger,
        )
        ingestion_service = IngestionService(
            knowledge_store=self.knowledge_store,
            property_store=self.property_store,
            pipeline_runner=pipeline_runner,
        )
        self.dashboard_service = DashboardQueryService(
            property_store=self.property_store,
            knowledge_store=self.knowledge_store,
        )
        self.snapshot_service = SnapshotService(
            property_store=self.property_store,
            rollup_store=rollup_store,
        )
        self.portfolio_query = PortfolioQueryService(property_store=self.property_store)
        self.manager_review = ManagerReviewService(property_store=self.property_store)
        self.rent_roll_service = RentRollService(property_store=self.property_store)
        self.auto_assign_service = AutoAssignService(
            property_store=self.property_store,
            knowledge_store=self.knowledge_store,
            snapshot_service=self.snapshot_service,
        )

        # -- Signal pipeline ---------------------------------------------------
        self.signal_pipeline = build_signal_pipeline(
            domain=mutable_tbox,
            property_store=self.property_store,
            signal_store=self.signal_store,
            snapshot_service=self.snapshot_service,
            knowledge_graph=self.knowledge_graph,
            tracer=tracer,
        )

        # -- Embedding pipeline ------------------------------------------------
        self.embedding_pipeline = EmbeddingPipeline(
            property_store=self.property_store,
            vector_store=self.vector_store,
            embedder=self.embedder,
            document_store=self.document_store,
            signal_store=self.signal_store,
        )

        # -- Search service ----------------------------------------------------
        self.search_service = SearchService(self.vector_store, self.embedder)

        # -- Document ingestion ------------------------------------------------
        self.document_ingest = DocumentIngestService(
            document_store=self.document_store,
            ingestion_service=ingestion_service,
            knowledge_store=self.knowledge_store,
            property_store=self.property_store,
            snapshot_service=self.snapshot_service,
            signal_pipeline=self.signal_pipeline,
            embedding_pipeline=self.embedding_pipeline,
            metadata_skip_patterns=self.profile.metadata_skip_patterns,
        )

        # -- Tools (phase 1 — before chat_agent exists) ------------------------
        _api_base = f"http://127.0.0.1:{self.settings.api.port}"
        register_all_tools(
            self.tool_registry,
            knowledge_graph=self.knowledge_graph,
            document_store=self.document_store,
            document_ingest=self.document_ingest,
            property_store=self.property_store,
            memory_store=memory_store,
            signal_store=self.signal_store,
            vector_store=self.vector_store,
            embedder=self.embedder,
            trace_store=self.trace_store,
            sandbox=self.sandbox,
            search_service=self.search_service,
            api_base_url=_api_base,
            profile=self.profile,
        )

        # -- Seed service ------------------------------------------------------
        store_bundle = self._build_store_bundle(rollup_store)
        self.seed_service = SeedService(
            document_ingest=self.document_ingest,
            auto_assign=self.auto_assign_service,
            signal_pipeline=self.signal_pipeline,
            embedding_pipeline=self.embedding_pipeline,
            property_store=self.property_store,
            snapshot_service=self.snapshot_service,
            rollup_store=rollup_store,
            store_bundle=store_bundle,
            metadata_skip_patterns=self.profile.metadata_skip_patterns,
        )

        # -- Chat agent --------------------------------------------------------
        context_builder = build_context_builder(
            domain=mutable_tbox,
            signal_store=self.signal_store,
            knowledge_graph=self.knowledge_graph,
            vector_store=self.vector_store,
            embedder=self.embedder,
            name_fields=self.profile.name_fields,
            empty_state_label=self.profile.empty_state_label,
        )
        self.chat_agent = ChatAgentService(
            provider_factory=self.provider_factory,
            tool_registry=self.tool_registry,
            sandbox=self.sandbox,
            domain_tbox=self.domain_tbox,
            signal_store=self.signal_store,
            memory_store=memory_store,
            tracer=tracer,
            chat_session_store=self.chat_session_store,
            retry_policy=RetryPolicy(
                max_retries=self.settings.execution.max_retries,
                delay_seconds=self.settings.execution.retry_delay_seconds,
            ),
            default_provider=self.settings.llm.default_provider,
            default_model=self.settings.llm.default_model,
            context_builder=context_builder,
            usage_ledger=self.usage_ledger,
        )

        # -- Tools (phase 2 — after chat_agent exists) -------------------------
        register_snapshot_tools(
            self.tool_registry,
            snapshot_service=self.snapshot_service,
        )
        register_workflow_tools(
            self.tool_registry,
            property_store=self.property_store,
            knowledge_graph=self.knowledge_graph,
            manager_review=self.manager_review,
            dashboard_service=self.dashboard_service,
            sub_agent=cast(SubAgentInvoker, self.chat_agent),
        )
        register_delegation_tools(
            self.tool_registry,
            agent_invoker=cast(AgentInvoker, self.chat_agent),
            available_agents=self.profile.available_agents,
        )
        register_assertion_tools(
            self.tool_registry,
            knowledge_graph=self.knowledge_graph,
        )

    def _build_store_bundle(self, rollup_store: RollupStore) -> StoreBundle | None:
        """Build a StoreBundle only when all stores are in-memory."""
        from remi.agent.documents.mem import InMemoryDocumentStore
        from remi.agent.graph.adapters.mem import InMemoryKnowledgeStore
        from remi.agent.signals.persistence.mem import InMemoryFeedbackStore, InMemorySignalStore
        from remi.application.infra.stores.mem import InMemoryPropertyStore
        from remi.application.infra.stores.rollups import InMemoryRollupStore

        if not (
            isinstance(self.property_store, InMemoryPropertyStore)
            and isinstance(self.knowledge_store, InMemoryKnowledgeStore)
            and isinstance(self.document_store, InMemoryDocumentStore)
            and isinstance(self.signal_store, InMemorySignalStore)
            and isinstance(self.feedback_store, InMemoryFeedbackStore)
            and isinstance(rollup_store, InMemoryRollupStore)
        ):
            return None

        return StoreBundle(
            property_store=self.property_store,
            knowledge_store=self.knowledge_store,
            document_store=self.document_store,
            signal_store=self.signal_store,
            feedback_store=self.feedback_store,
            rollup_store=rollup_store,
        )

    async def ensure_bootstrapped(self) -> None:
        if self._bootstrap_pending:
            if self._db_engine is not None:
                from remi.agent.db.engine import create_tables

                await create_tables(self._db_engine)
            await seed_knowledge_graph(self.knowledge_graph)
            self._bootstrap_pending = False
