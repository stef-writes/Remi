"""Dependency injection containers.

**InclineContainer** — domain-agnostic Incline framework wiring: graph runtime,
LLM providers, ontology system, entailment engine, sandbox, traces, tools.
Any product built on Incline uses this as its base.

**Container** — REMI (Real Estate Management Intelligence) product wiring.
Extends InclineContainer with PropertyStore, PM query services, RE-specific
ontology bindings, RE entailment evaluators, and the RE ingestion pipeline.
"""

from __future__ import annotations

from typing import Any

from remi.application.app_management.ports import AppRegistry
from remi.application.app_management.register_app import RegisterAppUseCase
from remi.application.app_management.validate_app import ValidateAppUseCase
from remi.application.chat.agent_runner import ChatAgentService
from remi.application.execution.run_app import RunAppUseCase
from remi.application.state_access.queries import StateQueryService
from remi.domain.chat.ports import ChatSessionStore
from remi.domain.documents.models import DocumentStore
from remi.domain.memory.ports import KnowledgeStore, MemoryStore
from remi.domain.modules.ports import ModuleRegistry
from remi.domain.retrieval.ports import Embedder, VectorStore
from remi.domain.sandbox.ports import Sandbox
from remi.domain.signals.feedback import FeedbackStore
from remi.domain.signals.ports import SignalStore
from remi.domain.signals.types import DomainOntology
from remi.domain.state.ports import StateStore
from remi.domain.tools.ports import ToolRegistry
from remi.domain.trace.ports import TraceStore
from remi.infrastructure.chat.in_memory import InMemoryChatSessionStore
from remi.infrastructure.config.settings import RemiSettings
from remi.infrastructure.documents.in_memory import InMemoryDocumentStore
from remi.infrastructure.entailment.composite import CompositeProducer
from remi.infrastructure.entailment.graduation import HypothesisGraduator, MutableDomainOntology
from remi.infrastructure.entailment.in_memory_feedback_store import InMemoryFeedbackStore
from remi.infrastructure.entailment.in_memory_hypothesis_store import InMemoryHypothesisStore
from remi.infrastructure.entailment.in_memory_signal_store import InMemorySignalStore
from remi.infrastructure.entailment.pattern_detector import PatternDetector
from remi.infrastructure.entailment.statistical import StatisticalProducer
from remi.infrastructure.llm.factory import LLMProviderFactory
from remi.infrastructure.memory.in_memory import InMemoryKnowledgeStore, InMemoryMemoryStore
from remi.infrastructure.ontology.bootstrap import bootstrap_ontology, load_domain_yaml
from remi.infrastructure.ontology.bridge import BridgedOntologyStore, CoreTypeBindings
from remi.infrastructure.registries.app_registry import InMemoryAppRegistry
from remi.infrastructure.registries.module_registry import InMemoryModuleRegistry
from remi.infrastructure.sandbox.local import LocalSandbox
from remi.infrastructure.sandbox.seeder import SandboxSeeder
from remi.infrastructure.stores.in_memory import InMemoryStateStore
from remi.infrastructure.tools import register_all_tools
from remi.infrastructure.tools.registry import InMemoryToolRegistry
from remi.infrastructure.trace.in_memory import InMemoryTraceStore
from remi.infrastructure.trace.tracer import Tracer
from remi.infrastructure.vectors.in_memory import InMemoryVectorStore
from remi.runtime.engine.graph_runner import GraphRunner
from remi.runtime.events.bus import EventBus, InMemoryEventBus
from remi.runtime.policies.retry import RetryPolicy
from remi.shared.clock import Clock, SystemClock


class InclineContainer:
    """Incline framework wiring — domain-agnostic AI infrastructure.

    Assembles: graph runtime, LLM providers, ontology system, entailment
    engine, signal pipeline, hypothesis pipeline, sandbox, trace layer,
    vector retrieval, tools, chat service, and platform API/CLI support.

    Product containers (like ``Container`` for REMI) extend this by
    providing domain-specific stores, core type bindings, entailment
    evaluators, and ingestion pipelines.
    """

    def __init__(self, settings: RemiSettings | None = None) -> None:
        self.settings = settings or RemiSettings()

        # -- Core infrastructure -----------------------------------------------
        self.clock: Clock = SystemClock()
        self.event_bus: EventBus = InMemoryEventBus()
        self.module_registry: ModuleRegistry = InMemoryModuleRegistry()
        self.app_registry: AppRegistry = InMemoryAppRegistry()
        self.state_store: StateStore = self._build_state_store()
        self.memory_store: MemoryStore = InMemoryMemoryStore()
        self.knowledge_store: KnowledgeStore = InMemoryKnowledgeStore()
        self.tool_registry: ToolRegistry = InMemoryToolRegistry()
        self.provider_factory: LLMProviderFactory = self._build_provider_factory()

        # -- Stores that products typically extend -----------------------------
        self.chat_session_store: ChatSessionStore = InMemoryChatSessionStore()
        self.document_store: DocumentStore = InMemoryDocumentStore()

        # -- Ontology layer (product provides core_types) ----------------------
        self.ontology_store: BridgedOntologyStore = BridgedOntologyStore(
            self.knowledge_store,
            core_types=self._build_core_type_bindings(),
        )
        self._bootstrap_pending = True

        # -- Trace layer -------------------------------------------------------
        self.trace_store: TraceStore = InMemoryTraceStore()
        self.tracer: Tracer = Tracer(self.trace_store)

        # -- Signal layer (TBox loaded from domain.yaml) -----------------------
        raw_domain = load_domain_yaml()
        self.domain_ontology: DomainOntology = DomainOntology.from_yaml(raw_domain)
        self.mutable_domain = MutableDomainOntology(self.domain_ontology)
        self.signal_store: SignalStore = InMemorySignalStore()
        self.feedback_store: FeedbackStore = InMemoryFeedbackStore()

        # -- Hypothesis layer --------------------------------------------------
        self.hypothesis_store = InMemoryHypothesisStore()
        self.pattern_detector = PatternDetector(
            ontology_store=self.ontology_store,
            hypothesis_store=self.hypothesis_store,
        )
        self.hypothesis_graduator = HypothesisGraduator(
            domain=self.mutable_domain,
            ontology_store=self.ontology_store,
            hypothesis_store=self.hypothesis_store,
        )

        # -- Sandbox -----------------------------------------------------------
        self.sandbox: Sandbox = LocalSandbox()

        # -- Vector retrieval --------------------------------------------------
        self.vector_store: VectorStore = InMemoryVectorStore()
        self.embedder: Embedder = self._build_embedder()

        # -- Tools (registered by subclass after domain wiring) ----------------
        self._register_builtins()

        # -- Execution layer ---------------------------------------------------
        self.retry_policy = RetryPolicy(
            max_retries=self.settings.execution.max_retries,
            delay_seconds=self.settings.execution.retry_delay_seconds,
        )

        context_extras: dict[str, Any] = {
            "tool_registry": self.tool_registry,
            "memory_store": self.memory_store,
            "knowledge_store": self.knowledge_store,
            "document_store": self.document_store,
            "app_registry": self.app_registry,
            "provider_factory": self.provider_factory,
            "ontology_store": self.ontology_store,
            "signal_store": self.signal_store,
            "domain_ontology": self.domain_ontology,
            "vector_store": self.vector_store,
            "embedder": self.embedder,
            "trace_store": self.trace_store,
            "tracer": self.tracer,
        }

        self.graph_runner = GraphRunner(
            module_registry=self.module_registry,
            state_store=self.state_store,
            event_bus=self.event_bus,
            clock=self.clock,
            retry_policy=self.retry_policy,
            context_extras=context_extras,
        )

        self.register_app_uc = RegisterAppUseCase(
            app_registry=self.app_registry,
            module_registry=self.module_registry,
        )
        self.validate_app_uc = ValidateAppUseCase(
            module_registry=self.module_registry,
        )
        self.run_app_uc = RunAppUseCase(
            app_registry=self.app_registry,
            graph_runner=self.graph_runner,
        )
        self.state_query = StateQueryService(
            state_store=self.state_store,
        )

        # -- Chat / agent service ----------------------------------------------
        self.chat_agent = ChatAgentService(
            register_app_uc=self.register_app_uc,
            run_app_uc=self.run_app_uc,
            state_query=self.state_query,
            chat_session_store=self.chat_session_store,
        )

    # -- Extension points for product containers -------------------------------

    def _build_core_type_bindings(self) -> CoreTypeBindings:
        """Override in product containers to provide domain store bindings."""
        return {}

    async def ensure_bootstrapped(self) -> None:
        if self._bootstrap_pending:
            await bootstrap_ontology(self.ontology_store)
            self._bootstrap_pending = False

    # -- Framework infrastructure builders ------------------------------------

    def _build_state_store(self) -> StateStore:
        backend = self.settings.state_store.backend
        if backend == "in_memory":
            return InMemoryStateStore()
        raise ValueError(f"Unsupported state store backend: {backend}")

    @staticmethod
    def _build_embedder() -> Embedder:
        import os

        if os.environ.get("OPENAI_API_KEY"):
            try:
                from remi.infrastructure.vectors.embedder import OpenAIEmbedder
                return OpenAIEmbedder()
            except Exception:
                pass
        from remi.infrastructure.vectors.embedder import NoopEmbedder
        return NoopEmbedder()

    @staticmethod
    def _build_provider_factory() -> LLMProviderFactory:
        factory = LLMProviderFactory()

        try:
            from remi.infrastructure.llm.openai_provider import OpenAIProvider
            factory.register("openai", OpenAIProvider)
            factory.register("openai_compatible", OpenAIProvider)
        except ImportError:
            pass

        try:
            from remi.infrastructure.llm.anthropic_provider import AnthropicProvider
            factory.register("anthropic", AnthropicProvider)
        except ImportError:
            pass

        try:
            from remi.infrastructure.llm.gemini_provider import GeminiProvider
            factory.register("gemini", GeminiProvider)
        except ImportError:
            pass

        return factory

    def _register_builtins(self) -> None:
        from remi.domain.modules.builtins.extract import ContextExtractorModule
        from remi.domain.modules.builtins.input import UserInputModule
        from remi.domain.modules.builtins.llm import AgentNode
        from remi.domain.modules.builtins.router import ConditionalRouterModule
        from remi.domain.modules.builtins.subgraph import SubgraphModule
        from remi.domain.modules.builtins.tool_call import ToolCallModule

        for cls in (
            UserInputModule,
            AgentNode,
            ConditionalRouterModule,
            ToolCallModule,
            ContextExtractorModule,
            SubgraphModule,
        ):
            self.module_registry.register(cls.kind, cls)

        self.module_registry.register("input", UserInputModule)


# =============================================================================
# REMI — Real Estate Management Intelligence (product container)
# =============================================================================


class Container(InclineContainer):
    """REMI product container — extends Incline with real estate domain wiring.

    Adds: PropertyStore, PM query services, RE ingestion pipeline, RE-specific
    entailment evaluators, sandbox seeder with RE data, and embedding pipeline.
    """

    def __init__(self, settings: RemiSettings | None = None) -> None:
        from remi.application.dashboard.service import DashboardQueryService
        from remi.application.document_management.ingest import DocumentIngestService
        from remi.application.property_management.lease_queries import LeaseQueryService
        from remi.application.property_management.maintenance_queries import MaintenanceQueryService
        from remi.application.property_management.manager_review import ManagerReviewService
        from remi.application.property_management.portfolio_queries import PortfolioQueryService
        from remi.application.property_management.property_queries import PropertyQueryService
        from remi.application.property_management.rent_roll import RentRollService
        from remi.application.snapshots.service import SnapshotService
        from remi.domain.properties.ports import PropertyStore
        from remi.infrastructure.entailment.engine import EntailmentEngine
        from remi.infrastructure.knowledge.ingestion import IngestionService
        from remi.infrastructure.properties.in_memory import InMemoryPropertyStore
        from remi.infrastructure.vectors.pipeline import EmbeddingPipeline

        # RE domain store — must be created before super().__init__ so
        # _build_core_type_bindings() can reference it
        self.property_store: PropertyStore = InMemoryPropertyStore()

        super().__init__(settings)

        # -- RE-specific services ----------------------------------------------

        self.ingestion_service = IngestionService(
            knowledge_store=self.knowledge_store,
            property_store=self.property_store,
        )

        self.dashboard_service = DashboardQueryService(
            property_store=self.property_store,
        )

        self.snapshot_service = SnapshotService(
            property_store=self.property_store,
        )

        self.property_query = PropertyQueryService(property_store=self.property_store)
        self.portfolio_query = PortfolioQueryService(property_store=self.property_store)
        self.lease_query = LeaseQueryService(property_store=self.property_store)
        self.maintenance_query = MaintenanceQueryService(property_store=self.property_store)
        self.manager_review = ManagerReviewService(property_store=self.property_store)
        self.rent_roll_service = RentRollService(property_store=self.property_store)

        # -- RE entailment engine (uses PropertyStore + SnapshotService) --------

        self.entailment_engine = EntailmentEngine(
            domain=self.mutable_domain,
            property_store=self.property_store,
            signal_store=self.signal_store,
            tracer=self.tracer,
            snapshot_service=self.snapshot_service,
        )
        self.statistical_producer = StatisticalProducer(
            ontology_store=self.ontology_store,
        )
        self.signal_pipeline = CompositeProducer(
            signal_store=self.signal_store,
            producers=[self.entailment_engine, self.statistical_producer],
            tracer=self.tracer,
        )

        # -- Sandbox seeder (exports RE data into sandbox) ---------------------

        api_url = f"http://{self.settings.api.host}:{self.settings.api.port}"
        self.sandbox_seeder = SandboxSeeder(
            property_store=self.property_store,
            signal_store=self.signal_store,
            ontology_store=self.ontology_store,
            api_base_url=api_url,
        )

        # -- Embedding pipeline (RE entities → vectors) ------------------------

        self.embedding_pipeline = EmbeddingPipeline(
            property_store=self.property_store,
            vector_store=self.vector_store,
            embedder=self.embedder,
            document_store=self.document_store,
        )

        # -- Tools (framework tools + any RE-specific tools) -------------------

        register_all_tools(
            self.tool_registry,
            ontology_store=self.ontology_store,
            document_store=self.document_store,
            memory_store=self.memory_store,
            signal_store=self.signal_store,
            vector_store=self.vector_store,
            embedder=self.embedder,
            trace_store=self.trace_store,
            sandbox=self.sandbox,
        )

        # -- RE document ingestion pipeline ------------------------------------

        self.document_ingest = DocumentIngestService(
            document_store=self.document_store,
            ingestion_service=self.ingestion_service,
            knowledge_store=self.knowledge_store,
            property_store=self.property_store,
            container=self,
        )

    def _build_core_type_bindings(self) -> CoreTypeBindings:
        """REMI core types: map RE entity names to PropertyStore methods."""
        return {
            "PropertyManager": (self.property_store.get_manager, self.property_store.list_managers),
            "Portfolio": (self.property_store.get_portfolio, self.property_store.list_portfolios),
            "Property": (self.property_store.get_property, self.property_store.list_properties),
            "Unit": (self.property_store.get_unit, self.property_store.list_units),
            "Lease": (self.property_store.get_lease, self.property_store.list_leases),
            "Tenant": (self.property_store.get_tenant, self.property_store.list_tenants),
            "MaintenanceRequest": (
                self.property_store.get_maintenance_request,
                self.property_store.list_maintenance_requests,
            ),
        }
