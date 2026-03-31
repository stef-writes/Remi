"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from remi.infrastructure.config.container import Container
from remi.infrastructure.config.settings import load_settings
from remi.infrastructure.observability.logging import configure_logging
from remi.interfaces.api.agents.router import router as agents_router
from remi.interfaces.api.dashboard.router import router as dashboard_router
from remi.interfaces.api.documents.router import router as documents_router
from remi.interfaces.api.hypotheses.router import router as hypotheses_router
from remi.interfaces.api.leases.router import router as leases_router
from remi.interfaces.api.maintenance.router import router as maintenance_router
from remi.interfaces.api.managers.router import router as managers_router
from remi.interfaces.api.ontology.router import router as ontology_router
from remi.interfaces.api.platform.router import router as platform_router
from remi.interfaces.api.portfolios.router import router as portfolios_router
from remi.interfaces.api.properties.router import router as properties_router
from remi.interfaces.api.realtime.connection_manager import wire_event_bus
from remi.interfaces.api.realtime.router import router as realtime_router
from remi.interfaces.api.signals.router import router as signals_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    configure_logging(level=settings.logging.level, format=settings.logging.format)
    container = Container(settings=settings)
    app.state.container = container
    app.state.settings = settings
    wire_event_bus(container)
    _load_workflows(container)
    await container.ensure_bootstrapped()
    yield


def _load_workflows(container: Container) -> None:
    """Pre-load all YAML workflow definitions into the app registry."""
    from remi.infrastructure.loaders.yaml_loader import YamlAppLoader
    from remi.shared.paths import WORKFLOWS_DIR

    if not WORKFLOWS_DIR.exists():
        return
    loader = YamlAppLoader()
    for app_def in loader.load_directory(WORKFLOWS_DIR):
        container.register_app_uc.execute(app_def)


def create_app() -> FastAPI:
    application = FastAPI(
        title="REMI",
        description="Real Estate Management Intelligence — AI-powered property analytics and operations.",
        version="0.1.0",
        lifespan=lifespan,
    )

    settings = load_settings()
    origins = settings.api.cors_origins or ["http://localhost:3000"]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Property management domain
    application.include_router(managers_router, prefix="/api/v1")
    application.include_router(portfolios_router, prefix="/api/v1")
    application.include_router(properties_router, prefix="/api/v1")
    application.include_router(leases_router, prefix="/api/v1")
    application.include_router(maintenance_router, prefix="/api/v1")
    application.include_router(agents_router, prefix="/api/v1")
    application.include_router(documents_router, prefix="/api/v1")
    application.include_router(dashboard_router, prefix="/api/v1")
    application.include_router(signals_router, prefix="/api/v1")

    # Ontology (domain-agnostic — OntologyStore over HTTP)
    application.include_router(ontology_router, prefix="/api/v1")

    # Hypotheses (inductive knowledge discovery lifecycle)
    application.include_router(hypotheses_router, prefix="/api/v1")

    # Platform (apps, runs, health)
    application.include_router(platform_router, prefix="/api/v1")

    # Realtime (WebSocket)
    application.include_router(realtime_router)

    return application


app = create_app()
