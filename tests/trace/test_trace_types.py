"""Test trace domain types."""

from __future__ import annotations

from remi.domain.trace.types import Span, SpanKind, SpanStatus, new_span_id, new_trace_id


def test_new_trace_id_format() -> None:
    tid = new_trace_id()
    assert tid.startswith("trace-")
    assert len(tid) == 18  # "trace-" + 12 hex chars


def test_new_span_id_format() -> None:
    sid = new_span_id()
    assert sid.startswith("span-")
    assert len(sid) == 17  # "span-" + 12 hex chars


def test_span_finish_sets_duration() -> None:
    s = Span(trace_id="t-1", kind=SpanKind.ENTAILMENT, name="test")
    assert s.duration_ms is None
    assert s.status == SpanStatus.RUNNING

    s.finish(SpanStatus.OK)
    assert s.ended_at is not None
    assert s.duration_ms is not None
    assert s.duration_ms >= 0
    assert s.status == SpanStatus.OK


def test_span_finish_with_extra_attrs() -> None:
    s = Span(trace_id="t-1", kind=SpanKind.TOOL_CALL, name="onto_explain")
    s.finish(SpanStatus.OK, result_count=5)
    assert s.attributes["result_count"] == 5


def test_span_add_event() -> None:
    s = Span(trace_id="t-1", kind=SpanKind.ENTAILMENT, name="detect")
    s.add_event("signal_produced", signal_type="VacancyDuration")
    assert len(s.events) == 1
    assert s.events[0].name == "signal_produced"
    assert s.events[0].attributes["signal_type"] == "VacancyDuration"
