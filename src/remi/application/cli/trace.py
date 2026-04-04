"""remi trace — reasoning and perception trace inspection.

Traces capture the full chain: entailment → perception → LLM calls →
tool calls → reasoning output. Every trace is a tree of spans that shows
*how* the system arrived at its conclusions.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from remi.agent.observe.types import Span
from remi.application.cli.shared import get_container_async, json_out, use_json

cmd = typer.Typer(
    name="trace",
    help="Inspect reasoning and perception traces.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# remi trace list
# ---------------------------------------------------------------------------


@cmd.command("list")
def list_traces(
    limit: int = typer.Option(20, "--limit", "-l", help="Max traces to show"),
    kind: str | None = typer.Option(None, "--kind", "-k", help="Filter by span kind"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List recent traces."""
    asyncio.run(_list_traces(limit, kind, use_json(json_output)))


async def _list_traces(limit: int, kind: str | None, fmt_json: bool) -> None:
    container = await get_container_async()
    traces = await container.trace_store.list_traces(limit=limit, kind=kind)
    items = [
        {
            "trace_id": t.trace_id,
            "started_at": t.started_at.isoformat(),
            "ended_at": t.ended_at.isoformat() if t.ended_at else None,
            "root": t.root_span_name,
            "spans": t.span_count,
            "status": t.status.value,
        }
        for t in traces
    ]
    if fmt_json:
        json_out({"count": len(items), "traces": items})
    else:
        if not items:
            typer.echo("\nNo traces recorded yet.")
            return
        typer.echo(f"\n{len(items)} trace(s):\n")
        for t in items:
            status_icon = "✓" if t["status"] == "ok" else "✗"
            typer.echo(
                f"  {status_icon} {t['trace_id']}  {t['root']:30s}  "
                f"{t['spans']} spans  {t['started_at']}"
            )


# ---------------------------------------------------------------------------
# remi trace show <trace-id>
# ---------------------------------------------------------------------------


@cmd.command("show")
def show(
    trace_id: str = typer.Argument(..., help="Trace ID to display"),
    kind: str | None = typer.Option(None, "--kind", "-k", help="Filter spans by kind"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Show the full span tree for a trace."""
    asyncio.run(_show(trace_id, kind, use_json(json_output)))


async def _show(trace_id: str, kind: str | None, fmt_json: bool) -> None:
    container = await get_container_async()
    spans = await container.trace_store.list_spans(trace_id)
    if not spans:
        if fmt_json:
            json_out({"ok": False, "error": f"Trace '{trace_id}' not found"})
        else:
            typer.echo(f"Trace not found: {trace_id}")
        raise typer.Exit(1)

    if kind is not None:
        spans = [s for s in spans if s.kind.value == kind]

    if fmt_json:
        json_out(
            {
                "trace_id": trace_id,
                "span_count": len(spans),
                "spans": [
                    {
                        "span_id": s.span_id,
                        "parent_span_id": s.parent_span_id,
                        "kind": s.kind.value,
                        "name": s.name,
                        "status": s.status.value,
                        "started_at": s.started_at.isoformat(),
                        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                        "duration_ms": s.duration_ms,
                        "attributes": s.attributes,
                        "events": [
                            {
                                "name": e.name,
                                "timestamp": e.timestamp.isoformat(),
                                "attributes": e.attributes,
                            }
                            for e in s.events
                        ],
                    }
                    for s in spans
                ],
            }
        )
    else:
        _render_span_tree(trace_id, spans)


def _render_span_tree(trace_id: str, spans: list[Any]) -> None:
    """Render spans as an indented tree to the terminal."""

    root_span = min(spans, key=lambda s: s.started_at)
    last_span = max(spans, key=lambda s: s.ended_at or s.started_at)
    total_ms = (
        (last_span.ended_at - root_span.started_at).total_seconds() * 1000
        if last_span.ended_at
        else None
    )

    duration_str = f"({total_ms:.0f}ms)" if total_ms is not None else "(running)"
    typer.echo(f"\nTRACE {trace_id}  {root_span.started_at.isoformat()}  {duration_str}")
    typer.echo()

    children_map: dict[str | None, list[Span]] = {}
    for s in spans:
        children_map.setdefault(s.parent_span_id, []).append(s)

    _render_subtree(root_span, children_map, prefix="", is_last=True)


def _render_subtree(
    span: object,
    children_map: dict[str | None, Any],
    prefix: str,
    is_last: bool,
) -> None:
    connector = "└─" if is_last else "├─"
    kind_label = span.kind.value.upper()  # type: ignore[attr-defined]
    name = span.name  # type: ignore[attr-defined]
    status = span.status.value  # type: ignore[attr-defined]
    duration = span.duration_ms  # type: ignore[attr-defined]

    dur_str = f"{duration:.0f}ms" if duration is not None else "..."
    status_icon = "✓" if status == "ok" else ("✗" if status == "error" else "⋯")

    typer.echo(f"{prefix}{connector} {status_icon} {kind_label:12s} {name}  ({dur_str})")

    attrs = span.attributes  # type: ignore[attr-defined]
    child_prefix = prefix + ("   " if is_last else "│  ")

    _render_key_attributes(attrs, child_prefix)

    events = span.events  # type: ignore[attr-defined]
    for ev in events:
        ev_attrs = " ".join(f"{k}={v}" for k, v in ev.attributes.items()) if ev.attributes else ""
        typer.echo(f"{child_prefix}  ◆ {ev.name}  {ev_attrs}")

    children = children_map.get(span.span_id, [])  # type: ignore[attr-defined]
    for i, child in enumerate(children):
        _render_subtree(child, children_map, child_prefix, is_last=(i == len(children) - 1))


def _render_key_attributes(attrs: dict[str, Any], prefix: str) -> None:
    """Show the most important attributes inline, skip verbose ones."""
    skip_keys = {"error"}
    for key, value in attrs.items():
        if key in skip_keys:
            continue
        if isinstance(value, dict) and len(str(value)) > 120:
            typer.echo(f"{prefix}  {key}: {{{len(value)} keys}}")
        elif isinstance(value, list) and len(value) > 5:
            typer.echo(f"{prefix}  {key}: [{len(value)} items]")
        elif isinstance(value, str) and len(value) > 120:
            typer.echo(f"{prefix}  {key}: {value[:120]}...")
        else:
            typer.echo(f"{prefix}  {key}: {value}")


# ---------------------------------------------------------------------------
# remi trace spans <trace-id>
# ---------------------------------------------------------------------------


@cmd.command("spans")
def spans(
    trace_id: str = typer.Argument(..., help="Trace ID"),
    kind: str | None = typer.Option(None, "--kind", "-k", help="Filter by span kind"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List spans in a trace as a flat table."""
    asyncio.run(_spans(trace_id, kind, use_json(json_output)))


async def _spans(trace_id: str, kind: str | None, fmt_json: bool) -> None:
    container = await get_container_async()
    all_spans = await container.trace_store.list_spans(trace_id)
    if kind is not None:
        all_spans = [s for s in all_spans if s.kind.value == kind]

    if fmt_json:
        json_out(
            {
                "trace_id": trace_id,
                "count": len(all_spans),
                "spans": [
                    {
                        "span_id": s.span_id,
                        "kind": s.kind.value,
                        "name": s.name,
                        "duration_ms": s.duration_ms,
                        "status": s.status.value,
                        "event_count": len(s.events),
                        "attribute_keys": list(s.attributes.keys()),
                    }
                    for s in all_spans
                ],
            }
        )
    else:
        if not all_spans:
            typer.echo(f"No spans found for trace {trace_id}")
            return
        typer.echo(f"\n{len(all_spans)} span(s) in trace {trace_id}:\n")
        for s in all_spans:
            dur = f"{s.duration_ms:.0f}ms" if s.duration_ms is not None else "..."
            typer.echo(
                f"  {s.kind.value:12s} {s.name:35s} {dur:>8s}  "
                f"{len(s.events)} events  {s.status.value}"
            )
