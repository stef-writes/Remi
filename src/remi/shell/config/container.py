"""REMI dependency injection container — RE product composition root.

Boots the Agent OS kernel via ``Kernel.boot()``, then layers the real
estate product on top: domain stores, resolvers, tool providers, and
domain schema.

The kernel owns generic infrastructure (LLM, sandbox, memory, events,
tasks, sessions, vectors, tools). This container adds product-specific
wiring that makes it the REMI real estate platform.
"""

from __future__ import annotations

from remi.agent.context import build_context_builder
from remi.agent.documents import ContentStore
from remi.agent.events import EventBuffer, EventBus
from remi.agent.graph import WorldModel
from remi.agent.llm import LLMProviderFactory
from remi.agent.observe import LLMUsageLedger
from remi.agent.observe.types import TraceStore
from remi.agent.profile import DomainProfile
from remi.agent.runtime.runner import AgentRuntime
from remi.agent.sandbox import Sandbox
from remi.agent.serve import Kernel, KernelSettings
from remi.agent.signals import DomainSchema, load_domain_yaml
from remi.agent.tasks import TaskSupervisor
from remi.agent.types import ChatSessionStore, ToolProvider, ToolRegistry
from remi.agent.vectors import Embedder, VectorStore
from remi.agent.workforce import Workforce
from remi.application.context import REEntityViewEnricher
from remi.application.core import EventStore, PropertyStore
from remi.application.ingestion import (
    DocumentIngestService,
    FormatRegistry,
    InMemoryFormatRegistry,
)
from remi.application.intelligence import SearchService, TrendResolver
from remi.application.operations import (
    DelinquencyResolver,
    LeaseResolver,
    MaintenanceResolver,
    VacancyResolver,
)
from remi.application.portfolio import (
    AutoAssignService,
    DashboardBuilder,
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
from remi.application.ingestion.tools import IngestionToolProvider
from remi.application.tools import DocumentToolProvider, MutationToolProvider, QueryToolProvider
from remi.application.tools.schemas import infer_result_schema
from remi.shell.config.settings import RemiSettings


class Container:
    """REMI container — boots kernel, layers RE product on top."""

    def __init__(self, settings: RemiSettings | None = None) -> None:
        self.settings = settings or RemiSettings()

        # -- Register capabilities (agent manifests) ---------------------------
        from remi.shell.config.capabilities import ensure_capabilities_registered
        from remi.types.paths import REMI_PACKAGE_DIR

        ensure_capabilities_registered()
        domain_yaml_path = REMI_PACKAGE_DIR / "shell" / "config" / "domain.yaml"

        # -- Domain schema + profile -------------------------------------------
        raw_domain = load_domain_yaml(domain_yaml_path)
        domain_schema: DomainSchema = DomainSchema.from_yaml(raw_domain)
        profile: DomainProfile = build_re_profile()

        # -- Boot the kernel (pass the registry capabilities already populated) -
        from remi.agent.workflow.registry import default_registry

        kernel_settings = KernelSettings(
            secrets=self.settings.secrets,
            llm=self.settings.llm,
            sandbox=self.settings.sandbox,
            embeddings=self.settings.embeddings,
            vectors=self.settings.vectors,
            memory=self.settings.memory,
            tracing=self.settings.tracing,
            sessions=self.settings.sessions,
            event_bus=self.settings.event_bus,
            task_queue=self.settings.task_queue,
            dsn=self.settings.state_store.dsn or self.settings.secrets.database_url,
            max_retries=self.settings.execution.max_retries,
            retry_delay_seconds=self.settings.execution.retry_delay_seconds,
            api_url=self.settings.api.resolved_internal_url(),
        )
        self._kernel = Kernel.boot(
            kernel_settings,
            domain_schema=domain_schema,
            registry=default_registry(),
        )

        # -- Expose kernel subsystems for product code -------------------------
        self.event_bus: EventBus = self._kernel.event_bus
        self.event_buffer: EventBuffer = self._kernel.event_buffer
        self.tool_registry: ToolRegistry = self._kernel.tool_registry
        self.provider_factory: LLMProviderFactory = self._kernel.provider_factory
        self.sandbox: Sandbox = self._kernel.sandbox
        self.vector_store: VectorStore = self._kernel.vector_store
        self.embedder: Embedder = self._kernel.embedder
        self.domain_schema: DomainSchema = domain_schema
        self.trace_store: TraceStore = self._kernel.trace_store
        self.usage_ledger: LLMUsageLedger = self._kernel.usage_ledger
        self.chat_agent: AgentRuntime = self._kernel.runtime
        self.task_supervisor: TaskSupervisor = self._kernel.supervisor
        self.workforce: Workforce = self._kernel.workforce

        # -- RE product stores -------------------------------------------------
        dsn = kernel_settings.dsn
        self._store_suite: StoreSuite = build_store_suite(
            backend=self.settings.state_store.backend,
            dsn=dsn,
        )
        self.property_store: PropertyStore = self._store_suite.property_store
        self.content_store: ContentStore = self._store_suite.content_store
        self._bootstrap_pending = True

        # -- RE event store ----------------------------------------------------
        self.event_store: EventStore = InMemoryEventStore()

        # -- RE resolvers — portfolio ------------------------------------------
        self.manager_resolver = ManagerResolver(property_store=self.property_store)
        self.property_resolver = PropertyResolver(property_store=self.property_store)
        self.rent_roll_resolver = RentRollResolver(property_store=self.property_store)
        self.dashboard_builder = DashboardBuilder(property_store=self.property_store)
        self.auto_assign_service = AutoAssignService(property_store=self.property_store)

        # -- RE resolvers — operations -----------------------------------------
        self.lease_resolver = LeaseResolver(property_store=self.property_store)
        self.maintenance_resolver = MaintenanceResolver(property_store=self.property_store)
        self.delinquency_resolver = DelinquencyResolver(property_store=self.property_store)
        self.vacancy_resolver = VacancyResolver(property_store=self.property_store)

        # -- RE resolvers — intelligence ----------------------------------------
        vector_search = AgentVectorSearch(self.vector_store, self.embedder)
        self.search_service = SearchService(vector_search)
        self.trend_resolver = TrendResolver(property_store=self.property_store)

        # -- RE format registry ------------------------------------------------
        self.format_registry: FormatRegistry = InMemoryFormatRegistry()

        # -- RE document ingestion ---------------------------------------------
        self.document_ingest = DocumentIngestService(
            content_store=self.content_store,
            property_store=self.property_store,
            event_bus=self.event_bus,
            metadata_skip_patterns=profile.metadata_skip_patterns,
            section_labels=profile.section_labels,
        )

        # -- RE world model (domain → kernel graph bridge) ---------------------
        self.world_model: WorldModel = build_re_world_model(self.property_store)

        # -- RE entity view enricher — pre-fetches live data for resolved entities
        self._enricher = REEntityViewEnricher(
            manager_resolver=self.manager_resolver,
            property_resolver=self.property_resolver,
        )

        # -- Upgrade kernel context builder with RE world model + enricher -----
        self.chat_agent.set_context_builder(build_context_builder(
            domain=domain_schema,
            world_model=self.world_model,
            vector_store=self.vector_store,
            embedder=self.embedder,
            name_fields=profile.name_fields,
            empty_state_label=profile.empty_state_label,
            enricher=self._enricher,
        ))

        # -- Inject result-schema inference (application → kernel boundary) ---
        self.chat_agent.set_result_schema_fn(infer_result_schema)

        # -- RE tool providers -------------------------------------------------
        re_providers: list[ToolProvider] = [
            QueryToolProvider(
                manager_resolver=self.manager_resolver,
                property_resolver=self.property_resolver,
                rent_roll_resolver=self.rent_roll_resolver,
                dashboard_builder=self.dashboard_builder,
                lease_resolver=self.lease_resolver,
                maintenance_resolver=self.maintenance_resolver,
                delinquency_resolver=self.delinquency_resolver,
                vacancy_resolver=self.vacancy_resolver,
                search_service=self.search_service,
                trend_resolver=self.trend_resolver,
                property_store=self.property_store,
                domain_schema=self.domain_schema,
            ),
            DocumentToolProvider(
                content_store=self.content_store,
                property_store=self.property_store,
                document_ingest=self.document_ingest,
                vector_search=vector_search,
            ),
            MutationToolProvider(
                property_store=self.property_store,
                event_store=self.event_store,
                event_bus=self.event_bus,
            ),
            IngestionToolProvider(
                content_store=self.content_store,
                property_store=self.property_store,
                event_bus=self.event_bus,
                format_registry=self.format_registry,
            ),
        ]
        for provider in re_providers:
            provider.register(self.tool_registry)

    async def ensure_bootstrapped(self) -> None:
        if self._bootstrap_pending:
            await self._store_suite.ensure_tables_created()
            self._bootstrap_pending = False
