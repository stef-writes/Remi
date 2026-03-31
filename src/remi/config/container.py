"""REMI dependency injection container.

Single container class wiring all REMI services: property store, ontology,
entailment engine, signal pipeline, sandbox, LLM providers, tools, chat,
and document ingestion.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from remi.agent.retry import RetryPolicy
from remi.agent.runner import ChatAgentService
from remi.config.settings import RemiSettings
from remi.documents.appfolio_schema import REPORT_TYPE_DESCRIPTIONS
from remi.knowledge.composite import CompositeProducer
from remi.knowledge.context_builder import ContextBuilder
from remi.knowledge.graduation import HypothesisGraduator
from remi.knowledge.graph_retriever import GraphRetriever
from remi.knowledge.ontology_bootstrap import bootstrap_ontology, load_domain_yaml
from remi.knowledge.ontology_bridge import BridgedOntologyStore, CoreTypeBindings
from remi.knowledge.pattern_detector import PatternDetector
from remi.knowledge.statistical import StatisticalProducer
from remi.llm.factory import LLMProviderFactory
from remi.models.signals import DomainOntology, FeedbackStore, MutableDomainOntology, SignalStore
from remi.observability.tracer import Tracer
from remi.sandbox.local import LocalSandbox
from remi.shared.clock import Clock, SystemClock
from remi.stores.chat import InMemoryChatSessionStore
from remi.stores.documents import InMemoryDocumentStore
from remi.stores.memory import InMemoryKnowledgeStore, InMemoryMemoryStore
from remi.stores.signals import InMemoryFeedbackStore, InMemoryHypothesisStore, InMemorySignalStore
from remi.stores.trace import InMemoryTraceStore
from remi.stores.vectors import InMemoryVectorStore
from remi.tools import register_all_tools
from remi.tools.registry import InMemoryToolRegistry

if TYPE_CHECKING:
    from remi.models.chat import ChatSessionStore
    from remi.models.documents import Document, DocumentStore
    from remi.models.memory import KnowledgeStore, MemoryStore
    from remi.models.properties import PropertyStore
    from remi.models.retrieval import Embedder, VectorStore
    from remi.models.sandbox import Sandbox
    from remi.models.tools import ToolRegistry
    from remi.models.trace import TraceStore


class Container:
    """REMI container — wires all services for the real estate product."""

    def __init__(self, settings: RemiSettings | None = None) -> None:
        from remi.knowledge.entailment import EntailmentEngine
        from remi.knowledge.ingestion import IngestionService
        from remi.services.auto_assign import AutoAssignService
        from remi.services.dashboard import DashboardQueryService
        from remi.services.document_ingest import DocumentIngestService, _parse_and_store
        from remi.services.lease_queries import LeaseQueryService
        from remi.services.maintenance_queries import MaintenanceQueryService
        from remi.services.manager_review import ManagerReviewService
        from remi.services.portfolio_queries import PortfolioQueryService
        from remi.services.property_queries import PropertyQueryService
        from remi.services.rent_roll import RentRollService
        from remi.services.snapshots import SnapshotService
        from remi.vectors.pipeline import EmbeddingPipeline

        self.settings = settings or RemiSettings()

        # -- Core infrastructure -----------------------------------------------
        self.clock: Clock = SystemClock()
        self.memory_store: MemoryStore = InMemoryMemoryStore()
        self.knowledge_store: KnowledgeStore = InMemoryKnowledgeStore()
        self.tool_registry: ToolRegistry = InMemoryToolRegistry()
        self.provider_factory: LLMProviderFactory = self._build_provider_factory()

        # -- Stores ------------------------------------------------------------
        self.chat_session_store: ChatSessionStore = InMemoryChatSessionStore()
        self.document_store: DocumentStore = InMemoryDocumentStore()
        self.property_store: PropertyStore = self._build_property_store()

        # -- Ontology layer ----------------------------------------------------
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
        api_url = f"http://127.0.0.1:{self.settings.api.port}"
        self.sandbox: Sandbox = LocalSandbox(
            extra_env={"REMI_API_URL": api_url},
        )

        # -- Vector retrieval --------------------------------------------------
        self.vector_store: VectorStore = InMemoryVectorStore()
        self.embedder: Embedder = self._build_embedder()

        # -- Retry policy ------------------------------------------------------
        self.retry_policy = RetryPolicy(
            max_retries=self.settings.execution.max_retries,
            delay_seconds=self.settings.execution.retry_delay_seconds,
        )

        # -- RE-specific services ----------------------------------------------

        async def _classify_document(doc: Document) -> str | None:
            if not self.settings.secrets.has_any_llm_key:
                return None
            try:
                answer, _run_id = await self.chat_agent.ask(
                    "report_classifier",
                    json.dumps(
                        {
                            "column_names": doc.column_names,
                            "sample_rows": doc.rows[:5],
                            "known_types": [
                                {"type": k, "description": v}
                                for k, v in REPORT_TYPE_DESCRIPTIONS.items()
                            ],
                        },
                        default=str,
                    ),
                )
                if not answer:
                    return None
                if isinstance(answer, str):
                    answer = json.loads(answer)
                if isinstance(answer, dict):
                    report_type = answer.get("report_type", "").strip().lower().replace(" ", "_")
                    return report_type if report_type else None
            except Exception:
                return None
            return None

        self.ingestion_service = IngestionService(
            knowledge_store=self.knowledge_store,
            property_store=self.property_store,
            classify_fn=_classify_document,
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
        self.auto_assign_service = AutoAssignService(
            property_store=self.property_store,
            knowledge_store=self.knowledge_store,
            snapshot_service=self.snapshot_service,
        )

        # -- Entailment engine -------------------------------------------------

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

        # -- Embedding pipeline ------------------------------------------------

        self.embedding_pipeline = EmbeddingPipeline(
            property_store=self.property_store,
            vector_store=self.vector_store,
            embedder=self.embedder,
            document_store=self.document_store,
        )

        # -- Tools -------------------------------------------------------------

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

        # -- Document ingestion pipeline ---------------------------------------

        async def _enrich_rows(
            rows: list[dict[str, Any]],
            doc: Document,
            knowledge_store: KnowledgeStore,
        ) -> tuple[int, int]:
            if not self.settings.secrets.has_any_llm_key:
                return 0, 0
            namespace = f"doc:{doc.id}"
            batch_size = 20
            total_entities = 0
            total_rels = 0
            try:
                for i in range(0, len(rows), batch_size):
                    batch = rows[i : i + batch_size]
                    payload = json.dumps(
                        [{"row_index": i + j, **row} for j, row in enumerate(batch)],
                        default=str,
                    )
                    answer, _run_id = await self.chat_agent.ask(
                        "knowledge_enricher",
                        payload,
                    )
                    if answer:
                        e, r = await _parse_and_store(answer, namespace, knowledge_store)
                        total_entities += e
                        total_rels += r
            except Exception:
                return total_entities, total_rels
            return total_entities, total_rels

        self.document_ingest = DocumentIngestService(
            document_store=self.document_store,
            ingestion_service=self.ingestion_service,
            knowledge_store=self.knowledge_store,
            property_store=self.property_store,
            snapshot_service=self.snapshot_service,
            signal_pipeline=self.signal_pipeline,
            pattern_detector=self.pattern_detector,
            embedding_pipeline=self.embedding_pipeline,
            enrich_fn=_enrich_rows,
        )

        # -- Knowledge retrieval -----------------------------------------------

        self.graph_retriever = GraphRetriever(
            ontology_store=self.ontology_store,
            vector_store=self.vector_store,
            embedder=self.embedder,
            signal_store=self.signal_store,
        )
        self.context_builder = ContextBuilder(
            domain=self.mutable_domain,
            signal_store=self.signal_store,
            graph_retriever=self.graph_retriever,
        )

        # -- Chat / agent service ----------------------------------------------

        self.chat_agent = ChatAgentService(
            provider_factory=self.provider_factory,
            tool_registry=self.tool_registry,
            sandbox=self.sandbox,
            domain_ontology=self.domain_ontology,
            signal_store=self.signal_store,
            memory_store=self.memory_store,
            tracer=self.tracer,
            chat_session_store=self.chat_session_store,
            retry_policy=self.retry_policy,
            default_provider=self.settings.llm.default_provider,
            default_model=self.settings.llm.default_model,
            context_builder=self.context_builder,
        )

    async def ensure_bootstrapped(self) -> None:
        if self._bootstrap_pending:
            if self._db_engine is not None:
                from remi.db.engine import create_tables

                await create_tables(self._db_engine)
            await bootstrap_ontology(self.ontology_store)
            self._bootstrap_pending = False

    def _build_property_store(self) -> PropertyStore:
        from remi.stores.properties import InMemoryPropertyStore

        self._db_engine = None
        self._db_session_factory = None

        backend = self.settings.state_store.backend
        if backend == "postgres":
            dsn = self.settings.state_store.dsn or self.settings.secrets.database_url
            if not dsn:
                raise ValueError(
                    "state_store.backend is 'postgres' but no DATABASE_URL or "
                    "state_store.dsn is configured."
                )
            from remi.db.engine import async_session_factory, create_async_engine_from_url
            from remi.stores.postgres import PostgresPropertyStore

            self._db_engine = create_async_engine_from_url(dsn)
            self._db_session_factory = async_session_factory(self._db_engine)
            return PostgresPropertyStore(self._db_session_factory)

        return InMemoryPropertyStore()

    def _build_core_type_bindings(self) -> CoreTypeBindings:
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

    def _build_embedder(self) -> Embedder:
        cfg = self.settings.embeddings
        provider = cfg.provider.lower()

        if provider == "openai":
            api_key = self.settings.secrets.openai_api_key
            if api_key:
                from remi.vectors.embedder import OpenAIEmbedder

                return OpenAIEmbedder(
                    model=cfg.model,
                    api_key=api_key,
                    dimensions=cfg.dimensions,
                )

        elif provider == "voyage":
            api_key = self.settings.secrets.voyage_api_key
            if api_key:
                from remi.vectors.embedder import VoyageEmbedder

                return VoyageEmbedder(model=cfg.model, api_key=api_key)

        from remi.vectors.embedder import NoopEmbedder

        return NoopEmbedder()

    def _build_provider_factory(self) -> LLMProviderFactory:
        factory = LLMProviderFactory()
        secrets = self.settings.secrets

        try:
            from remi.llm.openai import OpenAIProvider

            factory.register(
                "openai",
                lambda **kw: OpenAIProvider(
                    api_key=kw.pop("api_key", None) or secrets.openai_api_key,
                    **kw,
                ),
            )
            factory.register(
                "openai_compatible",
                lambda **kw: OpenAIProvider(
                    api_key=kw.pop("api_key", None) or secrets.openai_api_key,
                    **kw,
                ),
            )
        except ImportError:
            pass

        try:
            from remi.llm.anthropic import AnthropicProvider

            factory.register(
                "anthropic",
                lambda **kw: AnthropicProvider(
                    api_key=kw.pop("api_key", None) or secrets.anthropic_api_key,
                    **kw,
                ),
            )
        except ImportError:
            pass

        try:
            from remi.llm.gemini import GeminiProvider

            factory.register(
                "gemini",
                lambda **kw: GeminiProvider(
                    api_key=kw.pop("api_key", None) or secrets.google_api_key,
                    **kw,
                ),
            )
        except ImportError:
            pass

        return factory
