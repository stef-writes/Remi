"""In-memory trace store implementation."""

from __future__ import annotations

from collections import defaultdict

from remi.models.trace import Span, SpanStatus, Trace, TraceStore


class InMemoryTraceStore(TraceStore):
    def __init__(self) -> None:
        self._spans: dict[str, Span] = {}
        self._by_trace: dict[str, list[str]] = defaultdict(list)

    async def put_span(self, span: Span) -> None:
        self._spans[span.span_id] = span
        if span.span_id not in self._by_trace[span.trace_id]:
            self._by_trace[span.trace_id].append(span.span_id)

    async def get_span(self, span_id: str) -> Span | None:
        return self._spans.get(span_id)

    async def list_spans(self, trace_id: str) -> list[Span]:
        span_ids = self._by_trace.get(trace_id, [])
        spans = [self._spans[sid] for sid in span_ids if sid in self._spans]
        return sorted(spans, key=lambda s: s.started_at)

    async def list_traces(
        self,
        *,
        limit: int = 50,
        kind: str | None = None,
    ) -> list[Trace]:
        traces: list[Trace] = []
        for trace_id, span_ids in self._by_trace.items():
            spans = [self._spans[sid] for sid in span_ids if sid in self._spans]
            if not spans:
                continue

            if kind is not None:
                spans_of_kind = [s for s in spans if s.kind.value == kind]
                if not spans_of_kind:
                    continue

            root = min(spans, key=lambda s: s.started_at)
            last = max(spans, key=lambda s: s.ended_at or s.started_at)
            has_error = any(s.status == SpanStatus.ERROR for s in spans)

            traces.append(
                Trace(
                    trace_id=trace_id,
                    started_at=root.started_at,
                    ended_at=last.ended_at,
                    root_span_name=root.name,
                    span_count=len(spans),
                    status=SpanStatus.ERROR if has_error else SpanStatus.OK,
                )
            )

        traces.sort(key=lambda t: t.started_at, reverse=True)
        return traces[:limit]

    async def get_trace(self, trace_id: str) -> Trace | None:
        span_ids = self._by_trace.get(trace_id)
        if not span_ids:
            return None
        spans = [self._spans[sid] for sid in span_ids if sid in self._spans]
        if not spans:
            return None

        root = min(spans, key=lambda s: s.started_at)
        last = max(spans, key=lambda s: s.ended_at or s.started_at)
        has_error = any(s.status == SpanStatus.ERROR for s in spans)

        return Trace(
            trace_id=trace_id,
            started_at=root.started_at,
            ended_at=last.ended_at,
            root_span_name=root.name,
            span_count=len(spans),
            status=SpanStatus.ERROR if has_error else SpanStatus.OK,
        )
