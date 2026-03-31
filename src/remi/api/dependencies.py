"""FastAPI dependency injection — narrow typed accessors for route handlers.

Each accessor extracts exactly one service or port from the container,
enforcing the triangle: Container (broad) → dependencies.py (mediates) →
routers (each endpoint declares only what it needs).

All accessor functions chain through ``get_container`` so that
``app.dependency_overrides[get_container]`` is sufficient to redirect
every downstream dependency (critical for test fixtures).
"""

from __future__ import annotations

from fastapi import Depends, Request

from remi.agent.runner import ChatAgentService
from remi.config.container import Container
from remi.config.settings import RemiSettings
from remi.knowledge.composite import CompositeProducer
from remi.knowledge.ontology_bridge import BridgedKnowledgeGraph
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


def get_property_store(c: Container = Depends(get_container)) -> PropertyStore:
    return c.property_store


def get_signal_store(c: Container = Depends(get_container)) -> SignalStore:
    return c.signal_store


def get_feedback_store(c: Container = Depends(get_container)) -> FeedbackStore:
    return c.feedback_store


def get_signal_pipeline(c: Container = Depends(get_container)) -> CompositeProducer:
    return c.signal_pipeline


def get_knowledge_graph(c: Container = Depends(get_container)) -> BridgedKnowledgeGraph:
    return c.knowledge_graph


def get_document_store(c: Container = Depends(get_container)) -> DocumentStore:
    return c.document_store


def get_document_ingest(c: Container = Depends(get_container)) -> DocumentIngestService:
    return c.document_ingest


def get_chat_agent(c: Container = Depends(get_container)) -> ChatAgentService:
    return c.chat_agent


def get_chat_session_store(c: Container = Depends(get_container)) -> ChatSessionStore:
    return c.chat_session_store


def get_dashboard_service(c: Container = Depends(get_container)) -> DashboardQueryService:
    return c.dashboard_service


def get_snapshot_service(c: Container = Depends(get_container)) -> SnapshotService:
    return c.snapshot_service


def get_knowledge_store(c: Container = Depends(get_container)) -> KnowledgeStore:
    return c.knowledge_store


def get_settings(c: Container = Depends(get_container)) -> RemiSettings:
    return c.settings


def get_provider_factory(c: Container = Depends(get_container)) -> LLMProviderFactory:
    return c.provider_factory


def get_property_query(c: Container = Depends(get_container)) -> PropertyQueryService:
    return c.property_query


def get_portfolio_query(c: Container = Depends(get_container)) -> PortfolioQueryService:
    return c.portfolio_query


def get_lease_query(c: Container = Depends(get_container)) -> LeaseQueryService:
    return c.lease_query


def get_maintenance_query(c: Container = Depends(get_container)) -> MaintenanceQueryService:
    return c.maintenance_query


def get_manager_review(c: Container = Depends(get_container)) -> ManagerReviewService:
    return c.manager_review


def get_rent_roll_service(c: Container = Depends(get_container)) -> RentRollService:
    return c.rent_roll_service


def get_auto_assign_service(c: Container = Depends(get_container)) -> AutoAssignService:
    return c.auto_assign_service
