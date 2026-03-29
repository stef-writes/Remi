"""Structured logging configuration using structlog.

When a trace is active (via the Tracer context manager), every log event
automatically includes ``trace_id`` and ``span_id`` fields so logs
correlate with the reasoning trace tree.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def _inject_trace_context(
    logger: Any, method_name: str, event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that adds trace_id/span_id from contextvars."""
    from remi.infrastructure.trace.tracer import get_current_span_id, get_current_trace_id

    trace_id = get_current_trace_id()
    if trace_id is not None and "trace_id" not in event_dict:
        event_dict["trace_id"] = trace_id
    span_id = get_current_span_id()
    if span_id is not None and "span_id" not in event_dict:
        event_dict["span_id"] = span_id
    return event_dict


def configure_logging(level: str = "INFO", format: str = "structured") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    if format == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_trace_context,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
