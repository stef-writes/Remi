"""Trace tools — let agents inspect their own reasoning traces.

Provides: trace_list, trace_show, trace_spans.
"""

from __future__ import annotations

from typing import Any

from remi.domain.trace.ports import TraceStore
from remi.domain.tools.ports import ToolArg, ToolDefinition, ToolRegistry


def register_trace_tools(
    registry: ToolRegistry,
    *,
    trace_store: TraceStore | None = None,
) -> None:
    if trace_store is None:
        return

    # -- trace_list ------------------------------------------------------------

    async def trace_list(args: dict[str, Any]) -> Any:
        limit = int(args.get("limit", 10))
        kind = args.get("kind")
        traces = await trace_store.list_traces(limit=limit, kind=kind)
        return {
            "count": len(traces),
            "traces": [
                {
                    "trace_id": t.trace_id,
                    "started_at": t.started_at.isoformat(),
                    "root": t.root_span_name,
                    "spans": t.span_count,
                    "status": t.status.value,
                }
                for t in traces
            ],
        }

    registry.register(
        "trace_list",
        trace_list,
        ToolDefinition(
            name="trace_list",
            description="List recent reasoning traces. Each trace captures a full chain of entailment, perception, and reasoning.",
            args=[
                ToolArg(name="limit", description="Max traces to return (default 10)"),
                ToolArg(name="kind", description="Filter by span kind: entailment, perception, llm_call, tool_call, reasoning"),
            ],
        ),
    )

    # -- trace_show ------------------------------------------------------------

    async def trace_show(args: dict[str, Any]) -> Any:
        trace_id = args.get("trace_id", "")
        if not trace_id:
            return {"error": "trace_id is required"}

        spans = await trace_store.list_spans(trace_id)
        if not spans:
            return {"error": f"Trace '{trace_id}' not found"}

        kind = args.get("kind")
        if kind:
            spans = [s for s in spans if s.kind.value == kind]

        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "spans": [
                {
                    "span_id": s.span_id,
                    "parent_span_id": s.parent_span_id,
                    "kind": s.kind.value,
                    "name": s.name,
                    "status": s.status.value,
                    "duration_ms": s.duration_ms,
                    "attributes": s.attributes,
                    "events": [
                        {"name": e.name, "attributes": e.attributes}
                        for e in s.events
                    ],
                }
                for s in spans
            ],
        }

    registry.register(
        "trace_show",
        trace_show,
        ToolDefinition(
            name="trace_show",
            description=(
                "Show the full span tree for a reasoning trace. Reveals the chain: "
                "entailment → perception → LLM calls → tool calls → reasoning output. "
                "Use this to explain HOW you arrived at a conclusion."
            ),
            args=[
                ToolArg(name="trace_id", description="Trace ID to inspect", required=True),
                ToolArg(name="kind", description="Filter spans by kind"),
            ],
        ),
    )

    # -- trace_spans -----------------------------------------------------------

    async def trace_spans(args: dict[str, Any]) -> Any:
        trace_id = args.get("trace_id", "")
        if not trace_id:
            return {"error": "trace_id is required"}

        spans = await trace_store.list_spans(trace_id)
        kind = args.get("kind")
        if kind:
            spans = [s for s in spans if s.kind.value == kind]

        return {
            "trace_id": trace_id,
            "count": len(spans),
            "spans": [
                {
                    "kind": s.kind.value,
                    "name": s.name,
                    "duration_ms": s.duration_ms,
                    "event_count": len(s.events),
                }
                for s in spans
            ],
        }

    registry.register(
        "trace_spans",
        trace_spans,
        ToolDefinition(
            name="trace_spans",
            description="List spans in a trace as a flat summary.",
            args=[
                ToolArg(name="trace_id", description="Trace ID", required=True),
                ToolArg(name="kind", description="Filter by span kind"),
            ],
        ),
    )
