"""Tracer — ergonomic span creation and context propagation.

Usage:

    tracer = Tracer(trace_store)
    async with tracer.start_trace("entailment.run_all") as ctx:
        async with ctx.span(SpanKind.ENTAILMENT, "detect_vacancy") as child:
            child.add_event("signal_produced", signal_type="VacancyDuration")
            child.set_attribute("signals_produced", 3)

The tracer propagates trace_id and parent_span_id automatically via
contextvars so nested spans form a tree without manual threading.
"""

from __future__ import annotations

import contextvars
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from remi.domain.trace.types import (
    Span,
    SpanKind,
    SpanStatus,
    new_span_id,
    new_trace_id,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from remi.domain.trace.ports import TraceStore

_current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_trace_id", default=None
)
_current_span_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_span_id", default=None
)


def get_current_trace_id() -> str | None:
    return _current_trace_id.get()


def get_current_span_id() -> str | None:
    return _current_span_id.get()


class SpanContext:
    """Handle to a running span with convenience methods."""

    def __init__(self, span: Span, store: TraceStore) -> None:
        self._span = span
        self._store = store

    @property
    def span(self) -> Span:
        return self._span

    @property
    def trace_id(self) -> str:
        return self._span.trace_id

    @property
    def span_id(self) -> str:
        return self._span.span_id

    def set_attribute(self, key: str, value: Any) -> None:
        self._span.attributes[key] = value

    def add_event(self, name: str, **attrs: Any) -> None:
        self._span.add_event(name, **attrs)

    @asynccontextmanager
    async def span(
        self,
        kind: SpanKind,
        name: str,
        **attributes: Any,
    ) -> AsyncIterator[SpanContext]:
        """Create a child span under this span."""
        child = Span(
            trace_id=self._span.trace_id,
            span_id=new_span_id(),
            parent_span_id=self._span.span_id,
            kind=kind,
            name=name,
            attributes=dict(attributes) if attributes else {},
        )
        await self._store.put_span(child)

        token = _current_span_id.set(child.span_id)
        ctx = SpanContext(child, self._store)
        try:
            yield ctx
        except Exception as exc:
            child.finish(SpanStatus.ERROR, error=str(exc))
            await self._store.put_span(child)
            raise
        else:
            child.finish(SpanStatus.OK)
            await self._store.put_span(child)
        finally:
            _current_span_id.reset(token)


class Tracer:
    """Entry point for creating traces and spans."""

    def __init__(self, store: TraceStore) -> None:
        self._store = store

    @asynccontextmanager
    async def start_trace(
        self,
        name: str,
        kind: SpanKind = SpanKind.GRAPH,
        trace_id: str | None = None,
        **attributes: Any,
    ) -> AsyncIterator[SpanContext]:
        """Begin a new trace with a root span."""
        tid = trace_id or new_trace_id()
        root = Span(
            trace_id=tid,
            span_id=new_span_id(),
            parent_span_id=None,
            kind=kind,
            name=name,
            attributes=dict(attributes) if attributes else {},
        )
        await self._store.put_span(root)

        trace_token = _current_trace_id.set(tid)
        span_token = _current_span_id.set(root.span_id)
        ctx = SpanContext(root, self._store)
        try:
            yield ctx
        except Exception as exc:
            root.finish(SpanStatus.ERROR, error=str(exc))
            await self._store.put_span(root)
            raise
        else:
            root.finish(SpanStatus.OK)
            await self._store.put_span(root)
        finally:
            _current_span_id.reset(span_token)
            _current_trace_id.reset(trace_token)

    @asynccontextmanager
    async def span(
        self,
        kind: SpanKind,
        name: str,
        trace_id: str | None = None,
        **attributes: Any,
    ) -> AsyncIterator[SpanContext]:
        """Create a span within the current trace context.

        If no trace is active, creates an orphan span (useful for
        standalone operations like entailment runs triggered by CLI).
        """
        tid = trace_id or get_current_trace_id() or new_trace_id()
        parent = get_current_span_id()

        s = Span(
            trace_id=tid,
            span_id=new_span_id(),
            parent_span_id=parent,
            kind=kind,
            name=name,
            attributes=dict(attributes) if attributes else {},
        )
        await self._store.put_span(s)

        trace_token = _current_trace_id.set(tid)
        span_token = _current_span_id.set(s.span_id)
        ctx = SpanContext(s, self._store)
        try:
            yield ctx
        except Exception as exc:
            s.finish(SpanStatus.ERROR, error=str(exc))
            await self._store.put_span(s)
            raise
        else:
            s.finish(SpanStatus.OK)
            await self._store.put_span(s)
        finally:
            _current_span_id.reset(span_token)
            _current_trace_id.reset(trace_token)
