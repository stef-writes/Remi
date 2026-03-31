"""FastAPI application factory.

``create_app()`` builds the standalone server used by ``remi serve``.
It creates its own Container in the lifespan and manages the full lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from remi.api.actions.router import router as actions_router
from remi.api.notes.router import router as notes_router
from remi.api.agents.router import router as agents_router
from remi.api.dashboard.router import router as dashboard_router
from remi.api.documents.router import router as documents_router
from remi.api.leases.router import router as leases_router
from remi.api.maintenance.router import router as maintenance_router
from remi.api.managers.router import router as managers_router
from remi.api.ontology.router import router as ontology_router
from remi.api.portfolios.router import router as portfolios_router
from remi.api.properties.router import router as properties_router
from remi.api.realtime.router import router as realtime_router
from remi.api.seed.router import router as seed_router
from remi.api.signals.router import router as signals_router
from remi.api.tenants.router import router as tenants_router
from remi.api.units.router import router as units_router
from remi.api.error_handler import install_error_handlers
from remi.api.middleware import RequestIDMiddleware
from remi.config.container import Container
from remi.config.settings import RemiSettings, load_settings
from remi.observability.events import Event
from remi.observability.logging import configure_logging


def _attach_routers(application: FastAPI) -> None:
    application.include_router(managers_router, prefix="/api/v1")
    application.include_router(portfolios_router, prefix="/api/v1")
    application.include_router(properties_router, prefix="/api/v1")
    application.include_router(leases_router, prefix="/api/v1")
    application.include_router(maintenance_router, prefix="/api/v1")
    application.include_router(agents_router, prefix="/api/v1")
    application.include_router(documents_router, prefix="/api/v1")
    application.include_router(dashboard_router, prefix="/api/v1")
    application.include_router(signals_router, prefix="/api/v1")
    application.include_router(tenants_router, prefix="/api/v1")
    application.include_router(units_router, prefix="/api/v1")
    application.include_router(ontology_router, prefix="/api/v1")
    application.include_router(seed_router, prefix="/api/v1")
    application.include_router(actions_router, prefix="/api/v1")
    application.include_router(notes_router, prefix="/api/v1")
    application.include_router(realtime_router)


def _add_cors(application: FastAPI, settings: RemiSettings) -> None:
    origins = settings.api.cors_origins or ["http://localhost:3000"]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# -- Standalone server (``remi serve``) ------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    import os

    import structlog

    settings = load_settings()
    configure_logging(level=settings.logging.level, format=settings.logging.format)
    log = structlog.get_logger("remi.server")

    container = Container(settings=settings)
    app.state.container = container
    app.state.settings = settings
    await container.ensure_bootstrapped()

    log.info(
        Event.SERVER_READY,
        provider=settings.llm.default_provider,
        model=settings.llm.default_model,
        tools=len(container.tool_registry.list_tools()),
        environment=settings.environment,
    )

    if os.environ.pop("REMI_SEED_DEMO", None):
        from remi.cli.seed import seed_into

        await seed_into(container.property_store)
        result = await container.signal_pipeline.run_all()
        log.info("seed_signals_complete", produced=result.produced)
        embed_result = await container.embedding_pipeline.run_full()
        log.info("seed_embeddings_complete", embedded=embed_result.embedded)

    yield
    log.info(Event.SERVER_SHUTDOWN)


def create_app() -> FastAPI:
    application = FastAPI(
        title="REMI",
        description=(
            "Real Estate Management Intelligence — AI-powered property analytics and operations."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    install_error_handlers(application)
    application.add_middleware(RequestIDMiddleware)
    _add_cors(application, load_settings())
    _attach_routers(application)
    _attach_health(application)
    return application


def _attach_health(application: FastAPI) -> None:
    """Add ``/health`` endpoint for live assessment."""
    import time as _time

    _boot_time = _time.time()

    @application.get("/health", tags=["ops"])
    async def health() -> dict:
        container: Container | None = getattr(application.state, "container", None)
        trace_count = 0
        span_count = 0
        if container is not None:
            store = container.trace_store
            if hasattr(store, "_by_trace"):
                trace_count = len(store._by_trace)
                span_count = len(store._spans)
        uptime_s = round(_time.time() - _boot_time)
        return {
            "status": "ok",
            "version": application.version,
            "uptime_s": uptime_s,
            "traces": trace_count,
            "spans": span_count,
        }


app = create_app()
