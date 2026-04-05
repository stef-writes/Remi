"""Trace models and the Tracer runtime — span creation and context propagation.

The Tracer and SpanContext live here (not in infra/) because they have zero
infrastructure dependencies — they only use contextvars and the types below.
Domain and application code imports the Tracer from this module.
"""

from __future__ import annotations

import abc
import contextvars
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from enum import StrEnum, unique
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


def new_trace_id() -> str:
    return f"trace-{uuid.uuid4().hex[:12]}"


def new_span_id() -> str:
    return f"span-{uuid.uuid4().hex[:12]}"


@unique
class SpanKind(StrEnum):
    """Epistemological category of a span."""

    SIGNAL_PRODUCTION = "signal_production"
    PERCEPTION = "perception"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    REASONING = "reasoning"
    SIGNAL = "signal"
    GRAPH = "graph"
    MODULE = "module"


@unique
class SpanStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    ERROR = "error"


class SpanEvent(BaseModel, frozen=True):
    """A timestamped sub-event within a span."""

    name: str
    timestamp: datetime = Field(default_factory=_utcnow)
    attributes: dict[str, Any] = Field(default_factory=dict)


class Span(BaseModel):
    """A single unit of traced work within a reasoning chain."""

    trace_id: str
    span_id: str = Field(default_factory=new_span_id)
    parent_span_id: str | None = None
    kind: SpanKind
    name: str
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None
    status: SpanStatus = SpanStatus.RUNNING
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[SpanEvent] = Field(default_factory=list)

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds() * 1000

    def finish(self, status: SpanStatus = SpanStatus.OK, **attrs: Any) -> None:
        self.ended_at = _utcnow()
        self.status = status
        if attrs:
            self.attributes.update(attrs)

    def add_event(self, name: str, **attrs: Any) -> None:
        self.events.append(SpanEvent(name=name, attributes=attrs))


class Trace(BaseModel, frozen=True):
    """Summary view of a complete trace."""

    trace_id: str
    started_at: datetime
    ended_at: datetime | None = None
    root_span_name: str = ""
    span_count: int = 0
    status: SpanStatus = SpanStatus.OK
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceStore(abc.ABC):
    """Read/write access to trace spans."""

    @abc.abstractmethod
    async def put_span(self, span: Span) -> None: ...

    @abc.abstractmethod
    async def get_span(self, span_id: str) -> Span | None: ...

    @abc.abstractmethod
    async def list_spans(self, trace_id: str) -> list[Span]: ...

    @abc.abstractmethod
    async def list_traces(
        self,
        *,
        limit: int = 50,
        kind: str | None = None,
    ) -> list[Trace]: ...

    @abc.abstractmethod
    async def get_trace(self, trace_id: str) -> Trace | None: ...


# ---------------------------------------------------------------------------
# Tracer — ergonomic span creation and context propagation
# ---------------------------------------------------------------------------

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
    def as_span(self) -> Span:
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
