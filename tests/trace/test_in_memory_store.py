"""Test InMemoryTraceStore."""

from __future__ import annotations

import pytest

from remi.domain.trace.types import Span, SpanKind, SpanStatus, new_trace_id
from remi.infrastructure.trace.in_memory import InMemoryTraceStore


@pytest.fixture
def store() -> InMemoryTraceStore:
    return InMemoryTraceStore()


@pytest.mark.asyncio
async def test_put_and_get_span(store: InMemoryTraceStore) -> None:
    s = Span(trace_id="t-1", span_id="s-1", kind=SpanKind.ENTAILMENT, name="test")
    await store.put_span(s)
    got = await store.get_span("s-1")
    assert got is not None
    assert got.name == "test"


@pytest.mark.asyncio
async def test_list_spans_ordered_by_time(store: InMemoryTraceStore) -> None:
    tid = new_trace_id()
    s1 = Span(trace_id=tid, span_id="s-1", kind=SpanKind.ENTAILMENT, name="first")
    s2 = Span(trace_id=tid, span_id="s-2", kind=SpanKind.LLM_CALL, name="second")
    await store.put_span(s1)
    await store.put_span(s2)

    spans = await store.list_spans(tid)
    assert len(spans) == 2
    assert spans[0].started_at <= spans[1].started_at


@pytest.mark.asyncio
async def test_list_traces_returns_summary(store: InMemoryTraceStore) -> None:
    s = Span(trace_id="t-abc", span_id="s-1", kind=SpanKind.ENTAILMENT, name="root")
    s.finish(SpanStatus.OK)
    await store.put_span(s)

    traces = await store.list_traces()
    assert len(traces) == 1
    assert traces[0].trace_id == "t-abc"
    assert traces[0].root_span_name == "root"
    assert traces[0].span_count == 1


@pytest.mark.asyncio
async def test_get_trace(store: InMemoryTraceStore) -> None:
    s = Span(trace_id="t-xyz", span_id="s-1", kind=SpanKind.REASONING, name="output")
    s.finish(SpanStatus.OK)
    await store.put_span(s)

    trace = await store.get_trace("t-xyz")
    assert trace is not None
    assert trace.trace_id == "t-xyz"


@pytest.mark.asyncio
async def test_get_trace_not_found(store: InMemoryTraceStore) -> None:
    assert await store.get_trace("nonexistent") is None


@pytest.mark.asyncio
async def test_list_traces_with_kind_filter(store: InMemoryTraceStore) -> None:
    s1 = Span(trace_id="t-1", span_id="s-1", kind=SpanKind.ENTAILMENT, name="ent")
    s1.finish(SpanStatus.OK)
    await store.put_span(s1)

    s2 = Span(trace_id="t-2", span_id="s-2", kind=SpanKind.LLM_CALL, name="llm")
    s2.finish(SpanStatus.OK)
    await store.put_span(s2)

    ent_traces = await store.list_traces(kind="entailment")
    assert len(ent_traces) == 1
    assert ent_traces[0].trace_id == "t-1"


@pytest.mark.asyncio
async def test_error_status_propagates(store: InMemoryTraceStore) -> None:
    s1 = Span(trace_id="t-err", span_id="s-1", kind=SpanKind.ENTAILMENT, name="root")
    s1.finish(SpanStatus.OK)
    await store.put_span(s1)

    s2 = Span(trace_id="t-err", span_id="s-2", kind=SpanKind.LLM_CALL, name="fail")
    s2.finish(SpanStatus.ERROR, error="timeout")
    await store.put_span(s2)

    trace = await store.get_trace("t-err")
    assert trace is not None
    assert trace.status == SpanStatus.ERROR
