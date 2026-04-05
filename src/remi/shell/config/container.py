"""REMI dependency injection container — pure wiring only.

Calls factory functions from the modules that own the things being built.
No backend selection logic, no LLM adapter registration, no closures.

Only attributes read outside this module are stored as ``self.*``.
Internal intermediaries are local variables.
"""

from __future__ import annotations

from typing import cast

from remi.agent.context import build_context_builder
from remi.agent.documents import ContentStore
from remi.agent.graph import (
    BridgedKnowledgeGraph,
    GraphProjector,
    KnowledgeStore,
    MemoryStore,
    build_knowledge_store,
    build_memory_store,
)
from remi.agent.llm import LLMProviderFactory, build_provider_factory
from remi.agent.observe import LLMUsageLedger, Tracer, TraceStore, build_trace_store
from remi.agent.pipeline import IngestionPipelineRunner
from remi.agent.profile import DomainProfile
from remi.agent.runtime import ChatAgentService, RetryPolicy
from remi.agent.sandbox import Sandbox, build_sandbox
from remi.agent.sessions import build_chat_session_store
from remi.agent.signals import (
    DomainTBox,
    FeedbackStore,
    MutableTBox,
    SignalStore,
    build_feedback_store,
    build_signal_store,
)
from remi.agent.tools import (
    AgentInvoker,
    DelegationToolProvider,
    HttpToolProvider,
    InMemoryToolRegistry,
    MemoryToolProvider,
    SandboxToolProvider,
    TraceToolProvider,
    VectorToolProvider,
)
from remi.agent.types import ChatSessionStore, ToolArg, ToolProvider, ToolRegistry
from remi.agent.vectors import Embedder, VectorStore, build_embedder, build_vector_store
from remi.application.core import EventStore, PropertyStore
from remi.application.infra.ontology import (
    build_knowledge_graph,
    load_domain_yaml,
    seed_knowledge_graph,
)
from remi.application.infra.ports import (
    AgentTextIndexer,
    AgentVectorSearch,
    KnowledgeStoreReader,
    KnowledgeStoreWriter,
)
from remi.application.infra.stores import (
    InMemoryEventStore,
    ProjectingPropertyStore,
    StoreSuite,
    build_store_suite,
)
from remi.application.portfolio import (
    AutoAssignService,
    DashboardQueryService,
    DocumentResolver,
    LeaseResolver,
    MaintenanceResolver,
    ManagerReviewService,
    PortfolioResolver,
    PropertyResolver,
    RentRollService,
    SignalResolver,
    TenantResolver,
    UnitResolver,
)
from remi.application.profile import build_re_profile
from remi.application.services.embedding.pipeline import EmbeddingPipeline
from remi.application.services.ingestion.pipeline import DocumentIngestService
from remi.application.services.ingestion.service import IngestionService
from remi.application.services.search import SearchService
from remi.application.services.seeding import PortfolioLoader
from remi.application.tools import (
    ActionToolProvider,
    AssertionToolProvider,
    DocumentToolProvider,
    KnowledgeGraphToolProvider,
    SearchToolProvider,
    SubAgentInvoker,
    WorkflowToolProvider,
)
from remi.shell.config.settings import RemiSettings


def _build_scope_filter_args(profile: DomainProfile) -> list[ToolArg]:
    args: list[ToolArg] = []
    for key in ("manager_id", "property_id"):
        hint_key = f"semantic_search:{key}"
        desc = profile.tool_hints.get(hint_key, f"Filter results by {key}")
        args.append(ToolArg(name=key, description=desc))
    return args


class Container:
    """REMI container — wires all services for the real estate product."""

    def __init__(self, settings: RemiSettings | None = None) -> None:
        self.settings = settings or RemiSettings()

        # -- Domain profile (operational config for agent layer) ---------------
        self.profile: DomainProfile = build_re_profile()

        # -- Core infrastructure (all via factories) ---------------------------
        memory_store: MemoryStore = build_memory_store(self.settings)
        self.knowledge_store: KnowledgeStore = build_knowledge_store(self.settings)
        self.tool_registry: ToolRegistry = InMemoryToolRegistry()
        self.provider_factory: LLMProviderFactory = build_provider_factory(
            self.settings.secrets,
        )

        # -- Application stores (via StoreSuite) -------------------------------
        self.chat_session_store: ChatSessionStore = build_chat_session_store(self.settings)
        self._store_suite: StoreSuite = build_store_suite(self.settings)
        self.property_store: PropertyStore = self._store_suite.property_store
        self.content_store: ContentStore = self._store_suite.content_store

        # -- Knowledge graph ---------------------------------------------------
        self.knowledge_graph: BridgedKnowledgeGraph
        self.graph_projector: GraphProjector
        self.knowledge_graph, self.graph_projector = build_knowledge_graph(
            self.property_store,
            self.knowledge_store,
        )

        self.property_store = ProjectingPropertyStore(
            self.property_store, self.graph_projector
        )
        self._bootstrap_pending = True

        # -- Trace layer -------------------------------------------------------
        self.trace_store: TraceStore = build_trace_store(self.settings)
        self.usage_ledger: LLMUsageLedger = LLMUsageLedger()
        tracer = Tracer(self.trace_store)

        # -- Signal layer ------------------------------------------------------
        raw_domain = load_domain_yaml()
        self.domain_tbox: DomainTBox = DomainTBox.from_yaml(raw_domain)
        mutable_tbox = MutableTBox(self.domain_tbox)
        self.signal_store: SignalStore = build_signal_store(self.settings)
        self.feedback_store: FeedbackStore = build_feedback_store(self.settings)

        # -- Sandbox -----------------------------------------------------------
        self.sandbox: Sandbox = build_sandbox(self.settings)

        # -- Vectors -----------------------------------------------------------
        self.vector_store: VectorStore = build_vector_store(self.settings)
        self.embedder: Embedder = build_embedder(
            self.settings.embeddings,
            self.settings.secrets,
        )

        # -- Application-layer ports (bridge agent → application) ---------------
        self.knowledge_writer = KnowledgeStoreWriter(self.knowledge_store)
        self.knowledge_reader = KnowledgeStoreReader(self.knowledge_store)

        # -- Event store -------------------------------------------------------
        self.event_store: EventStore = InMemoryEventStore()

        # -- Services ----------------------------------------------------------
        pipeline_runner = IngestionPipelineRunner(
            provider_factory=self.provider_factory,
            default_provider=self.settings.llm.default_provider,
            default_model=self.settings.llm.default_model,
            usage_ledger=self.usage_ledger,
        )
        ingestion_service = IngestionService(
            knowledge_writer=self.knowledge_writer,
            property_store=self.property_store,
            pipeline_runner=pipeline_runner,
        )
        self.property_resolver = PropertyResolver(property_store=self.property_store)
        self.portfolio_resolver = PortfolioResolver(property_store=self.property_store)
        self.lease_resolver = LeaseResolver(property_store=self.property_store)
        self.maintenance_resolver = MaintenanceResolver(property_store=self.property_store)
        self.unit_resolver = UnitResolver(property_store=self.property_store)
        self.tenant_resolver = TenantResolver(property_store=self.property_store)
        self.signal_resolver = SignalResolver(signal_store=self.signal_store)
        self.document_resolver = DocumentResolver(property_store=self.property_store)
        self.manager_review = ManagerReviewService(property_store=self.property_store)
        self.rent_roll_service = RentRollService(property_store=self.property_store)
        self.dashboard_service = DashboardQueryService(
            property_store=self.property_store,
            knowledge_reader=self.knowledge_reader,
        )
        self.auto_assign_service = AutoAssignService(
            property_store=self.property_store,
            knowledge_reader=self.knowledge_reader,
        )

        # -- Embedding pipeline ------------------------------------------------
        text_indexer = AgentTextIndexer(self.embedder, self.vector_store)
        self.embedding_pipeline = EmbeddingPipeline(
            property_store=self.property_store,
            text_indexer=text_indexer,
            content_store=self.content_store,
            signal_store=self.signal_store,
        )

        # -- Search service ----------------------------------------------------
        vector_search = AgentVectorSearch(self.vector_store, self.embedder)
        self.search_service = SearchService(vector_search)

        # -- Document ingestion ------------------------------------------------
        self.document_ingest = DocumentIngestService(
            content_store=self.content_store,
            ingestion_service=ingestion_service,
            embedding_pipeline=self.embedding_pipeline,
            metadata_skip_patterns=self.profile.metadata_skip_patterns,
        )

        # -- Tool providers (phase 1 — before chat_agent exists) ---------------
        _api_base = f"http://127.0.0.1:{self.settings.api.port}"
        p = self.profile
        scope_args = _build_scope_filter_args(p) if p.scope_entity_type else []

        phase1_providers: list[ToolProvider] = [
            SandboxToolProvider(self.sandbox, data_bridge_hint=p.data_bridge_hint),
            HttpToolProvider(api_base_url=_api_base, api_path_examples=p.api_path_examples),
            MemoryToolProvider(memory_store),
            VectorToolProvider(
                self.vector_store,
                self.embedder,
                search_hint=p.tool_hints.get("semantic_search", ""),
                entity_type_hint=p.tool_hints.get("semantic_search:entity_type", ""),
                scope_filter_args=scope_args,
            ),
            TraceToolProvider(self.trace_store),
            KnowledgeGraphToolProvider(self.knowledge_graph, signal_store=self.signal_store),
            DocumentToolProvider(
                self.content_store,
                self.property_store,
                document_ingest=self.document_ingest,
                vector_search=vector_search,
            ),
            ActionToolProvider(self.property_store, knowledge_graph=self.knowledge_graph),
            SearchToolProvider(self.search_service),
        ]
        for provider in phase1_providers:
            provider.register(self.tool_registry)

        # -- Portfolio loader --------------------------------------------------
        self.portfolio_loader = PortfolioLoader(
            document_ingest=self.document_ingest,
            embedding_pipeline=self.embedding_pipeline,
            auto_assign=self.auto_assign_service,
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

        # -- Tool providers (phase 2 — after chat_agent exists) ----------------
        phase2_providers: list[ToolProvider] = [
            WorkflowToolProvider(
                self.property_store,
                self.knowledge_graph,
                self.manager_review,
                self.dashboard_service,
                sub_agent=cast(SubAgentInvoker, self.chat_agent),
            ),
            DelegationToolProvider(
                cast(AgentInvoker, self.chat_agent),
                self.profile.available_agents or {},
            ),
            AssertionToolProvider(self.knowledge_graph, event_store=self.event_store),
        ]
        for provider in phase2_providers:
            provider.register(self.tool_registry)

    async def ensure_bootstrapped(self) -> None:
        if self._bootstrap_pending:
            await self._store_suite.ensure_tables_created()
            await seed_knowledge_graph(self.knowledge_graph)
            self._bootstrap_pending = False
