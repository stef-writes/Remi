"""FastAPI dependency injection — narrow typed accessors for route handlers.

Each accessor extracts exactly one service or port from the container,
enforcing the triangle: Container (broad) → dependencies.py (mediates) →
routers (each endpoint declares only what it needs).
"""

from __future__ import annotations

from fastapi import Request

from remi.agent.runner import ChatAgentService
from remi.config.container import Container
from remi.config.settings import RemiSettings
from remi.knowledge.composite import CompositeProducer
from remi.knowledge.ontology_bridge import BridgedOntologyStore
from remi.llm.factory import LLMProviderFactory
from remi.models.chat import ChatSessionStore
from remi.models.documents import DocumentStore
from remi.models.memory import KnowledgeStore
from remi.models.properties import PropertyStore
from remi.models.signals import FeedbackStore, SignalStore
from remi.services.auto_assign import AutoAssignService
from remi.services.dashboard import DashboardQueryService
from remi.services.document_ingest import DocumentIngestService
from remi.services.lease_queries import LeaseQueryService
from remi.services.maintenance_queries import MaintenanceQueryService
from remi.services.manager_review import ManagerReviewService
from remi.services.portfolio_queries import PortfolioQueryService
from remi.services.property_queries import PropertyQueryService
from remi.services.rent_roll import RentRollService
from remi.services.snapshots import SnapshotService


def get_container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


def get_property_store(request: Request) -> PropertyStore:
    return request.app.state.container.property_store


def get_signal_store(request: Request) -> SignalStore:
    return request.app.state.container.signal_store


def get_feedback_store(request: Request) -> FeedbackStore:
    return request.app.state.container.feedback_store


def get_signal_pipeline(request: Request) -> CompositeProducer:
    return request.app.state.container.signal_pipeline


def get_ontology_store(request: Request) -> BridgedOntologyStore:
    return request.app.state.container.ontology_store


def get_document_store(request: Request) -> DocumentStore:
    return request.app.state.container.document_store


def get_document_ingest(request: Request) -> DocumentIngestService:
    return request.app.state.container.document_ingest


def get_chat_agent(request: Request) -> ChatAgentService:
    return request.app.state.container.chat_agent


def get_chat_session_store(request: Request) -> ChatSessionStore:
    return request.app.state.container.chat_session_store


def get_dashboard_service(request: Request) -> DashboardQueryService:
    return request.app.state.container.dashboard_service


def get_snapshot_service(request: Request) -> SnapshotService:
    return request.app.state.container.snapshot_service


def get_knowledge_store(request: Request) -> KnowledgeStore:
    return request.app.state.container.knowledge_store


def get_settings(request: Request) -> RemiSettings:
    return request.app.state.container.settings


def get_provider_factory(request: Request) -> LLMProviderFactory:
    return request.app.state.container.provider_factory


def get_property_query(request: Request) -> PropertyQueryService:
    return request.app.state.container.property_query


def get_portfolio_query(request: Request) -> PortfolioQueryService:
    return request.app.state.container.portfolio_query


def get_lease_query(request: Request) -> LeaseQueryService:
    return request.app.state.container.lease_query


def get_maintenance_query(request: Request) -> MaintenanceQueryService:
    return request.app.state.container.maintenance_query


def get_manager_review(request: Request) -> ManagerReviewService:
    return request.app.state.container.manager_review


def get_rent_roll_service(request: Request) -> RentRollService:
    return request.app.state.container.rent_roll_service


def get_auto_assign_service(request: Request) -> AutoAssignService:
    return request.app.state.container.auto_assign_service
