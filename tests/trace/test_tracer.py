"""Test Tracer context manager and span propagation."""

from __future__ import annotations

import pytest

from remi.domain.trace.types import SpanKind, SpanStatus
from remi.infrastructure.trace.in_memory import InMemoryTraceStore
from remi.infrastructure.trace.tracer import (
    Tracer,
    get_current_span_id,
    get_current_trace_id,
)


@pytest.fixture
def store() -> InMemoryTraceStore:
    return InMemoryTraceStore()


@pytest.fixture
def tracer(store: InMemoryTraceStore) -> Tracer:
    return Tracer(store)


@pytest.mark.asyncio
async def test_start_trace_creates_root_span(
    tracer: Tracer, store: InMemoryTraceStore,
) -> None:
    async with tracer.start_trace("test.root") as ctx:
        assert ctx.trace_id is not None
        assert ctx.span_id is not None

    spans = await store.list_spans(ctx.trace_id)
    assert len(spans) == 1
    assert spans[0].name == "test.root"
    assert spans[0].status == SpanStatus.OK
    assert spans[0].parent_span_id is None


@pytest.mark.asyncio
async def test_child_spans_form_tree(
    tracer: Tracer, store: InMemoryTraceStore,
) -> None:
    async with tracer.start_trace("root") as root:
        async with root.span(SpanKind.ENTAILMENT, "child1"):
            async with root.span(SpanKind.LLM_CALL, "child2"):
                pass

    spans = await store.list_spans(root.trace_id)
    assert len(spans) == 3

    root_span = next(s for s in spans if s.name == "root")
    child1 = next(s for s in spans if s.name == "child1")
    child2 = next(s for s in spans if s.name == "child2")

    assert root_span.parent_span_id is None
    assert child1.parent_span_id == root_span.span_id
    assert child2.parent_span_id == root_span.span_id


@pytest.mark.asyncio
async def test_nested_child_spans(
    tracer: Tracer, store: InMemoryTraceStore,
) -> None:
    async with tracer.start_trace("root") as root:
        async with root.span(SpanKind.ENTAILMENT, "parent") as parent:
            async with parent.span(SpanKind.SIGNAL, "grandchild"):
                pass

    spans = await store.list_spans(root.trace_id)
    assert len(spans) == 3

    parent_span = next(s for s in spans if s.name == "parent")
    grandchild = next(s for s in spans if s.name == "grandchild")

    assert grandchild.parent_span_id == parent_span.span_id


@pytest.mark.asyncio
async def test_contextvars_propagate(tracer: Tracer) -> None:
    assert get_current_trace_id() is None
    assert get_current_span_id() is None

    async with tracer.start_trace("test") as ctx:
        assert get_current_trace_id() == ctx.trace_id
        assert get_current_span_id() == ctx.span_id

    assert get_current_trace_id() is None
    assert get_current_span_id() is None


@pytest.mark.asyncio
async def test_error_marks_span(
    tracer: Tracer, store: InMemoryTraceStore,
) -> None:
    with pytest.raises(ValueError, match="boom"):
        async with tracer.start_trace("fail") as ctx:
            raise ValueError("boom")

    spans = await store.list_spans(ctx.trace_id)
    assert len(spans) == 1
    assert spans[0].status == SpanStatus.ERROR
    assert spans[0].attributes.get("error") == "boom"


@pytest.mark.asyncio
async def test_set_attribute_and_add_event(
    tracer: Tracer, store: InMemoryTraceStore,
) -> None:
    async with tracer.start_trace("annotated") as ctx:
        ctx.set_attribute("count", 42)
        ctx.add_event("something_happened", detail="yes")

    spans = await store.list_spans(ctx.trace_id)
    s = spans[0]
    assert s.attributes["count"] == 42
    assert len(s.events) == 1
    assert s.events[0].name == "something_happened"


@pytest.mark.asyncio
async def test_standalone_span_creates_own_trace(
    tracer: Tracer, store: InMemoryTraceStore,
) -> None:
    async with tracer.span(SpanKind.ENTAILMENT, "orphan") as ctx:
        pass

    spans = await store.list_spans(ctx.trace_id)
    assert len(spans) == 1
    assert spans[0].parent_span_id is None
