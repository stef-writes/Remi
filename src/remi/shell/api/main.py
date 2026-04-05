"""FastAPI application factory.

``create_app()`` builds the standalone server used by ``remi serve``.
It creates its own Container in the lifespan and manages the full lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from remi.agent.observe import Event, configure_logging
from remi.application.api.intelligence import (
    dashboard_router,
    events_router,
    knowledge_router,
    ontology_router,
    search_router,
    signals_router,
)
from remi.application.api.operations import (
    actions_router,
    leases_router,
    maintenance_router,
    notes_router,
    tenants_router,
)
from remi.application.api.portfolio import (
    managers_router,
    portfolios_router,
    properties_router,
    units_router,
)
from remi.application.api.system import (
    agents_router,
    documents_router,
    realtime_router,
    reports_router,
    usage_router,
)
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
    application.include_router(events_router, prefix="/api/v1")
    application.include_router(dashboard_router, prefix="/api/v1")
    application.include_router(signals_router, prefix="/api/v1")
    application.include_router(tenants_router, prefix="/api/v1")
    application.include_router(units_router, prefix="/api/v1")
    application.include_router(ontology_router, prefix="/api/v1")
    application.include_router(search_router, prefix="/api/v1")
    application.include_router(reports_router, prefix="/api/v1")
    application.include_router(actions_router, prefix="/api/v1")
    application.include_router(notes_router, prefix="/api/v1")
    application.include_router(usage_router, prefix="/api/v1")
    application.include_router(knowledge_router, prefix="/api/v1")
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

    load_task: asyncio.Task[None] | None = None
    report_dir = os.environ.pop("REMI_LOAD_DIR", None)
    if report_dir:
        load_task = asyncio.create_task(
            _load_reports_bg(container, Path(report_dir), log)
        )
    app.state.load_task = load_task

    yield
    if load_task and not load_task.done():
        load_task.cancel()
    log.info(Event.SERVER_SHUTDOWN)


async def _load_reports_bg(
    container: Container, report_dir: Path, log: Any,
) -> None:
    """Load reports in the background so the server starts accepting requests immediately."""
    try:
        result = await container.portfolio_loader.load_reports(report_dir)
        log.info(
            "load_reports_complete",
            files=result.files_processed,
            entities=result.total_entities,
            relationships=result.total_relationships,
            embedded=result.total_embedded,
            errors=len(result.errors),
        )
    except Exception:
        log.exception("load_reports_failed")


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

        load_task: _aio.Task[None] | None = getattr(application.state, "load_task", None)
        if load_task is None:
            load_status = "not_requested"
        elif not load_task.done():
            load_status = "running"
        elif load_task.exception():
            load_status = "failed"
        else:
            load_status = "complete"

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
            "data_load": load_status,
            "traces": trace_count,
            "spans": span_count,
            "llm_calls": llm_calls,
            "llm_total_tokens": llm_total_tokens,
            "llm_cost_usd": llm_cost_usd,
        }


app = create_app()
