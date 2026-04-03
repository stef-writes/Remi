"""FastAPI application factory.

``create_app()`` builds the standalone server used by ``remi serve``.
It creates its own Container in the lifespan and manages the full lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from remi.shell.api.agents.router import router as agents_router
from remi.shell.api.realtime.router import router as realtime_router
from remi.agent.observe.events import Event
from remi.shell.api.documents.router import router as documents_router
from remi.shell.api.ontology.router import router as ontology_router
from remi.shell.api.search_routes.router import router as search_router
from remi.shell.api.seed.router import router as seed_router
from remi.shell.api.signals.router import router as signals_router
from remi.shell.api.actions.router import router as actions_router
from remi.shell.api.dashboard.router import router as dashboard_router
from remi.shell.api.leases.router import router as leases_router
from remi.shell.api.maintenance.router import router as maintenance_router
from remi.shell.api.managers.router import router as managers_router
from remi.shell.api.notes.router import router as notes_router
from remi.shell.api.portfolios.router import router as portfolios_router
from remi.shell.api.properties.router import router as properties_router
from remi.shell.api.tenants.router import router as tenants_router
from remi.shell.api.units.router import router as units_router
from remi.shell.api.usage.router import router as usage_router
from remi.agent.observe.logging import configure_logging
from remi.shell.api.error_handler import install_error_handlers
from remi.shell.api.middleware import RequestIDMiddleware
from remi.shell.config.container import Container
from remi.shell.config.settings import RemiSettings, load_settings


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
    application.include_router(search_router, prefix="/api/v1")
    application.include_router(seed_router, prefix="/api/v1")
    application.include_router(actions_router, prefix="/api/v1")
    application.include_router(notes_router, prefix="/api/v1")
    application.include_router(usage_router, prefix="/api/v1")
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
    import asyncio
    import os

    import structlog

    settings: RemiSettings = app.state.settings
    configure_logging(level=settings.logging.level, format=settings.logging.format)
    log = structlog.get_logger("remi.server")

    container = Container(settings=settings)
    app.state.container = container
    await container.ensure_bootstrapped()

    log.info(
        Event.SERVER_READY,
        provider=settings.llm.default_provider,
        model=settings.llm.default_model,
        tools=len(container.tool_registry.list_tools()),
        environment=settings.environment,
    )

    seed_task: asyncio.Task[None] | None = None
    if os.environ.pop("REMI_SEED", None):
        seed_task = asyncio.create_task(_run_seed(container, log))
    app.state.seed_task = seed_task

    capture_task = asyncio.create_task(
        _periodic_capture(container, settings.api.capture_interval_minutes, log)
    )
    yield
    if seed_task and not seed_task.done():
        seed_task.cancel()
    capture_task.cancel()
    log.info(Event.SERVER_SHUTDOWN)


async def _run_seed(container: Container, log: Any) -> None:
    """Run seed in the background so the server starts accepting requests immediately."""
    try:
        seed_result = await container.seed_service.seed_from_reports()
        log.info(
            "seed_complete",
            managers=seed_result.managers_created,
            properties=seed_result.properties_created,
            reports=len(seed_result.reports_ingested),
            signals=seed_result.signals_produced,
            history_snapshots=seed_result.history_snapshots,
            errors=seed_result.errors,
        )
    except Exception:
        log.exception("seed_failed")


async def _periodic_capture(container: Container, interval_minutes: int, log: Any) -> None:
    """Background task: capture rollup snapshots on a fixed interval."""
    import asyncio

    interval = interval_minutes * 60
    while True:
        await asyncio.sleep(interval)
        try:
            snapshots = await container.snapshot_service.capture()
            log.info("periodic_capture_complete", managers=len(snapshots))
        except Exception:
            log.exception("periodic_capture_failed")


def create_app() -> FastAPI:
    settings = load_settings()
    application = FastAPI(
        title="REMI",
        description=(
            "Real Estate Management Intelligence — AI-powered property analytics and operations."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = settings
    install_error_handlers(application)
    _attach_routers(application)
    _attach_health(application)
    # Middleware executes in reverse-add order (last-added = outermost).
    # RequestID sits closest to the handler. CORS is outermost so its
    # headers appear on every response including errors.
    application.add_middleware(RequestIDMiddleware)
    _add_cors(application, settings)
    return application


def _attach_health(application: FastAPI) -> None:
    """Add ``/health`` endpoint for live assessment."""
    import time as _time

    _boot_time = _time.time()

    @application.get("/health", tags=["ops"])
    async def health() -> dict[str, Any]:
        import asyncio as _aio

        container: Container | None = getattr(application.state, "container", None)
        trace_count = 0
        span_count = 0
        if container is not None:
            store = container.trace_store
            if hasattr(store, "_by_trace") and hasattr(store, "_spans"):
                trace_count = len(store._by_trace)
                span_count = len(store._spans)
        uptime_s = round(_time.time() - _boot_time)

        seed_task: _aio.Task[None] | None = getattr(application.state, "seed_task", None)
        if seed_task is None:
            seed_status = "not_requested"
        elif not seed_task.done():
            seed_status = "running"
        elif seed_task.exception():
            seed_status = "failed"
        else:
            seed_status = "complete"

        llm_calls = 0
        llm_cost_usd = 0.0
        llm_total_tokens = 0
        if container is not None and hasattr(container, "usage_ledger"):
            usage = container.usage_ledger.summary()
            llm_calls = usage.total_calls
            llm_cost_usd = round(usage.total_estimated_cost_usd, 6)
            llm_total_tokens = usage.total_tokens

        return {
            "status": "ok",
            "version": application.version,
            "uptime_s": uptime_s,
            "seed": seed_status,
            "traces": trace_count,
            "spans": span_count,
            "llm_calls": llm_calls,
            "llm_total_tokens": llm_total_tokens,
            "llm_cost_usd": llm_cost_usd,
        }


app = create_app()
