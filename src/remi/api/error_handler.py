"""Global error-to-HTTP translation.

Registers a single ``exception_handler`` on the FastAPI app so that
every ``RemiError`` subclass is automatically mapped to a structured
JSON response with the correct HTTP status code.  Routers no longer
need to catch-and-wrap into ``HTTPException`` — just let typed errors
propagate.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog

from remi.observability.events import Event
from remi.shared.errors import (
    AgentConfigError,
    AppNotFoundError,
    DomainError,
    ExecutionError,
    IngestionError,
    LLMError,
    RemiError,
    RetryExhaustedError,
    SessionNotFoundError,
    ValidationError,
)

logger = structlog.get_logger("remi.error_handler")

_STATUS_MAP: list[tuple[type[RemiError], int]] = [
    (ValidationError, 422),
    (AppNotFoundError, 404),
    (SessionNotFoundError, 404),
    (AgentConfigError, 400),
    (DomainError, 400),
    (RetryExhaustedError, 502),
    (LLMError, 502),
    (IngestionError, 500),
    (ExecutionError, 502),
    (RemiError, 500),
]


def _status_for(exc: RemiError) -> int:
    for err_type, status in _STATUS_MAP:
        if isinstance(exc, err_type):
            return status
    return 500


async def _handle_remi_error(request: Request, exc: RemiError) -> JSONResponse:
    status = _status_for(exc)
    logger.error(
        Event.HTTP_ERROR_RESPONSE,
        error_code=exc.code,
        error_type=type(exc).__name__,
        status_code=status,
        path=request.url.path,
        method=request.method,
        detail=str(exc),
    )
    return JSONResponse(
        status_code=status,
        content={"error": exc.to_dict()},
    )


async def _handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        Event.UNHANDLED_ERROR,
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
        detail=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on *app*."""
    app.add_exception_handler(RemiError, _handle_remi_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unhandled)  # type: ignore[arg-type]
