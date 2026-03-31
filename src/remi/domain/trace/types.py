"""Trace types — structured spans capturing perception, reasoning, and action.

A Trace groups all spans produced during a single interaction: the entailment
engine evaluating rules, the agent receiving its world model, calling tools,
reasoning about signals, and producing output. Together the spans form a
hierarchical record of *how* the system arrived at its conclusions.

SpanKind encodes the epistemological category — not just "what happened" but
*what kind of cognitive act* the span represents.
"""

from __future__ import annotations

import uuid
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

    ENTAILMENT = "entailment"
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
