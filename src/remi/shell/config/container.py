"""REMI dependency injection container — pure wiring only.

Calls factory functions from the modules that own the things being built.
Only three kernel tool providers are registered: ``AnalysisToolProvider``
(python, bash), ``MemoryToolProvider`` (memory_store, memory_recall),
and ``DelegationToolProvider`` (delegate_to_agent). All domain data
access goes through the ``remi`` CLI.

Only attributes read outside this module are stored as ``self.*``.
Internal intermediaries are local variables.
"""

from __future__ import annotations

from remi.agent.context import build_context_builder
from remi.agent.documents import ContentStore
from remi.agent.events import DomainEvent, EventBuffer, EventBus, build_event_bus
from remi.agent.graph import WorldModel
from remi.agent.llm import LLMProviderFactory, build_provider_factory
from remi.agent.memory import MemoryStore, build_memory_store
from remi.agent.memory.recall import MemoryRecallService
from remi.agent.observe import LLMUsageLedger, Tracer, TraceStore, build_trace_store
from remi.agent.profile import DomainProfile
from remi.agent.runtime import AgentRuntime, RetryPolicy
from remi.agent.sandbox import Sandbox, build_sandbox
from remi.agent.sessions import build_chat_session_store
from remi.agent.signals import (
    DomainTBox,
    MutableTBox,
    load_domain_yaml,
    set_domain_yaml_path,
)
from remi.agent.tasks import TaskSupervisor, build_task_pool
from remi.agent.tools import (
    AnalysisToolProvider,
    DelegationToolProvider,
    InMemoryToolCatalog,
    MemoryToolProvider,
)
from remi.agent.types import ChatSessionStore, ToolProvider, ToolRegistry
from remi.agent.vectors import Embedder, VectorStore, build_embedder, build_vector_store
from remi.agent.workflow import WorkflowRunner
from remi.agent.workforce import Workforce
from remi.application.core import EventStore, PropertyStore
from remi.application.ingestion import DocumentIngestService
from remi.application.intelligence import (
    DashboardResolver,
    SearchService,
)
from remi.application.operations import (
    LeaseResolver,
    MaintenanceResolver,
)
from remi.application.portfolio import (
    AutoAssignService,
    ManagerResolver,
    PropertyResolver,
    RentRollResolver,
)
from remi.application.profile import build_re_profile
from remi.application.stores import (
    InMemoryEventStore,
    StoreSuite,
    build_store_suite,
)
from remi.application.stores.indexer import AgentVectorSearch
from remi.application.stores.world import build_re_world_model
from remi.shell.config.settings import RemiSettings


class Container:
    """REMI container — wires all services for the real estate product."""

    def __init__(self, settings: RemiSettings | None = None) -> None:
        self.settings = settings or RemiSettings()

        # -- Register capabilities (before any agent/ factories run) ------------
        from remi.shell.config.capabilities import ensure_capabilities_registered
        from remi.types.paths import DOMAIN_YAML_PATH

        ensure_capabilities_registered()
        set_domain_yaml_path(DOMAIN_YAML_PATH)

        # -- Domain profile (operational config for agent layer) ---------------
        profile: DomainProfile = build_re_profile()

        # -- Event bus + buffer (kernel infrastructure) -------------------------
        self.event_bus: EventBus = build_event_bus(self.settings.event_bus)
        self.event_buffer: EventBuffer = EventBuffer(capacity=8192)

        async def _buffer_sink(event: DomainEvent) -> None:
            await self.event_buffer.append(event)

        self.event_bus.subscribe("*", _buffer_sink)

        # -- Core infrastructure (all via factories) ---------------------------
        memory_store: MemoryStore = build_memory_store(self.settings)
        recall_service = MemoryRecallService(memory_store)
        self.tool_registry: ToolRegistry = InMemoryToolCatalog()
        self.provider_factory: LLMProviderFactory = build_provider_factory(
            self.settings.secrets,
        )

        # -- Application stores (via StoreSuite) -------------------------------
        self._chat_session_store: ChatSessionStore = build_chat_session_store(self.settings)
        self._store_suite: StoreSuite = build_store_suite(self.settings)
        self.property_store: PropertyStore = self._store_suite.property_store
        self.content_store: ContentStore = self._store_suite.content_store
        self._bootstrap_pending = True

        # -- Trace layer -------------------------------------------------------
        self.trace_store: TraceStore = build_trace_store(self.settings)
        self.usage_ledger: LLMUsageLedger = LLMUsageLedger()
        tracer = Tracer(self.trace_store)

        # -- Domain TBox -------------------------------------------------------
        raw_domain = load_domain_yaml()
        self.domain_tbox: DomainTBox = DomainTBox.from_yaml(raw_domain)
        mutable_tbox = MutableTBox(self.domain_tbox)

        # -- Sandbox -----------------------------------------------------------
        self.sandbox: Sandbox = build_sandbox(self.settings)

        # -- Vectors -----------------------------------------------------------
        self.vector_store: VectorStore = build_vector_store(self.settings)
        self.embedder: Embedder = build_embedder(
            self.settings.embeddings,
            self.settings.secrets,
        )

        # -- Event store -------------------------------------------------------
        self.event_store: EventStore = InMemoryEventStore()

        # -- Services ----------------------------------------------------------
        self.workflow_runner = WorkflowRunner(
            provider_factory=self.provider_factory,
            default_provider=self.settings.llm.default_provider,
            default_model=self.settings.llm.default_model,
            usage_ledger=self.usage_ledger,
            tool_registry=self.tool_registry,
        )
        self.property_resolver = PropertyResolver(property_store=self.property_store)
        self.lease_resolver = LeaseResolver(property_store=self.property_store)
        self.maintenance_resolver = MaintenanceResolver(property_store=self.property_store)
        self.manager_resolver = ManagerResolver(property_store=self.property_store)
        self.rent_roll_resolver = RentRollResolver(property_store=self.property_store)
        self.dashboard_resolver = DashboardResolver(
            property_store=self.property_store,
        )
        self.auto_assign_service = AutoAssignService(
            property_store=self.property_store,
        )

        # -- Search service ----------------------------------------------------
        vector_search = AgentVectorSearch(self.vector_store, self.embedder)
        self.search_service = SearchService(vector_search)

        # -- Document ingestion ------------------------------------------------
        self.document_ingest = DocumentIngestService(
            content_store=self.content_store,
            property_store=self.property_store,
            workflow_runner=self.workflow_runner,
            metadata_skip_patterns=profile.metadata_skip_patterns,
            section_labels=profile.section_labels,
        )

        # -- World model --------------------------------------------------------
        self.world_model: WorldModel = build_re_world_model(self.property_store)

        # -- Tool providers (kernel primitives only) ----------------------------
        kernel_providers: list[ToolProvider] = [
            AnalysisToolProvider(self.sandbox),
            MemoryToolProvider(memory_store),
        ]
        for provider in kernel_providers:
            provider.register(self.tool_registry)

        # -- Chat agent --------------------------------------------------------
        context_builder = build_context_builder(
            domain=mutable_tbox,
            world_model=self.world_model,
            vector_store=self.vector_store,
            embedder=self.embedder,
            name_fields=profile.name_fields,
            empty_state_label=profile.empty_state_label,
        )
        self.chat_agent = AgentRuntime(
            provider_factory=self.provider_factory,
            tool_registry=self.tool_registry,
            sandbox=self.sandbox,
            domain_tbox=self.domain_tbox,
            memory_store=memory_store,
            tracer=tracer,
            chat_session_store=self._chat_session_store,
            retry_policy=RetryPolicy(
                max_retries=self.settings.execution.max_retries,
                delay_seconds=self.settings.execution.retry_delay_seconds,
            ),
            default_provider=self.settings.llm.default_provider,
            default_model=self.settings.llm.default_model,
            context_builder=context_builder,
            usage_ledger=self.usage_ledger,
            recall_service=recall_service,
        )

        # -- Wire workflow engine ↔ agent runtime (bidirectional) --------------
        self.workflow_runner.set_agent_executor(self.chat_agent)

        # -- Task supervisor (kernel multi-agent coordination) -----------------
        task_pool = build_task_pool(self.settings.task_queue)
        self.task_supervisor = TaskSupervisor(
            executor=self.chat_agent,  # type: ignore[arg-type]
            event_bus=self.event_bus,
            pool=task_pool,
        )

        # -- Workforce (agent topology from manifests) -------------------------
        self.workforce = Workforce.from_registry()

        # -- Delegation tool (requires chat_agent → task_supervisor → workforce)
        DelegationToolProvider(
            self.task_supervisor,
            workforce=self.workforce,
        ).register(self.tool_registry)

    async def ensure_bootstrapped(self) -> None:
        if self._bootstrap_pending:
            await self._store_suite.ensure_tables_created()
            self._bootstrap_pending = False
