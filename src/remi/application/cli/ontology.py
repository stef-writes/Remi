"""remi onto — unified ontology queries, traversal, and knowledge codification.

Every command here is the authoritative implementation of an ontology
operation. Agent tools call these via _cli_exec, ensuring one code path.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import typer

from remi.application.cli import http as _http
from remi.application.cli.shared import get_container_async, json_out, parse_params, use_json


def _assert_writable() -> None:
    """Exit if running in read-only (ask) mode."""
    if os.environ.get("REMI_MODE") == "ask":
        typer.echo("Error: write operations are disabled in ask mode.", err=True)
        raise typer.Exit(1)


cmd = typer.Typer(name="onto", help="Query and extend the REMI ontology.", no_args_is_help=True)


# ---------------------------------------------------------------------------
# remi onto search <type_name>
# ---------------------------------------------------------------------------


@cmd.command("search")
def search(
    type_name: str = typer.Argument(..., help="Object type to search"),
    filter_: list[str] = typer.Option([], "--filter", "-f", help="Field filters as key=value"),
    order_by: str | None = typer.Option(
        None, "--order-by", "-o", help="Sort field (prefix with - for desc)"
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Search objects of any type with field filters."""
    asyncio.run(_search(type_name, filter_, order_by, limit, use_json(json_output)))


async def _search(
    type_name: str,
    raw_filters: list[str],
    order_by: str | None,
    limit: int,
    fmt_json: bool,
) -> None:
    container = await get_container_async()
    filters = parse_params(raw_filters) if raw_filters else None
    results = await container.knowledge_graph.search_objects(
        type_name,
        filters=filters,
        order_by=order_by,
        limit=limit,
    )
    if fmt_json:
        json_out({"count": len(results), "objects": [r.model_dump(mode="json") for r in results]})
    else:
        typer.echo(f"Found {len(results)} {type_name} object(s)")
        for obj in results:
            summary = json.dumps(obj.model_dump(mode="json"), default=str)[:120]
            typer.echo(f"  {obj.id:12s}  {summary}")


# ---------------------------------------------------------------------------
# remi onto get <type_name> <object_id>
# ---------------------------------------------------------------------------


@cmd.command("get")
def get(
    type_name: str = typer.Argument(..., help="Object type"),
    object_id: str = typer.Argument(..., help="Object ID"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Get a single object by type and ID."""
    asyncio.run(_get(type_name, object_id, use_json(json_output)))


async def _get(type_name: str, object_id: str, fmt_json: bool) -> None:
    container = await get_container_async()
    obj = await container.knowledge_graph.get_object(type_name, object_id)
    if obj is None:
        data = {"ok": False, "error": f"{type_name} '{object_id}' not found"}
        if fmt_json:
            json_out(data)
        else:
            typer.echo(f"Not found: {type_name} '{object_id}'")
        raise typer.Exit(1)
    if fmt_json:
        json_out(obj.model_dump(mode="json"))
    else:
        typer.echo(json.dumps(obj.model_dump(mode="json"), indent=2, default=str))


# ---------------------------------------------------------------------------
# remi onto related <object_id>
# ---------------------------------------------------------------------------


@cmd.command("related")
def related(
    object_id: str = typer.Argument(..., help="Object ID to find relationships for"),
    link_type: str | None = typer.Option(None, "--link-type", "-t", help="Filter by link type"),
    direction: str = typer.Option("both", "--direction", "-d", help="both|outgoing|incoming"),
    max_depth: int = typer.Option(
        1, "--max-depth", "-D", help="Traversal depth (1 = direct links only)"
    ),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Find related objects via link traversal."""
    asyncio.run(_related(object_id, link_type, direction, max_depth, use_json(json_output)))


async def _related(
    object_id: str,
    link_type: str | None,
    direction: str,
    max_depth: int,
    fmt_json: bool,
) -> None:
    container = await get_container_async()
    if max_depth > 1:
        link_types = [link_type] if link_type else None
        results = await container.knowledge_graph.traverse(
            object_id,
            link_types=link_types,
            max_depth=max_depth,
        )
        if fmt_json:
            json_out(
                {
                    "start": object_id,
                    "depth": max_depth,
                    "count": len(results),
                    "nodes": [n.model_dump(mode="json") for n in results],
                }
            )
        else:
            typer.echo(f"Traversal from {object_id} (depth={max_depth}): {len(results)} nodes")
            for node in results:
                typer.echo(f"  {node.id:20s}  {node.type_name:15s}")
    else:
        links = await container.knowledge_graph.get_links(
            object_id,
            link_type=link_type,
            direction=direction,
        )
        if fmt_json:
            json_out(
                {
                    "object_id": object_id,
                    "count": len(links),
                    "links": [lnk.model_dump(mode="json") for lnk in links],
                }
            )
        else:
            typer.echo(f"Links for {object_id}: {len(links)}")
            for lnk in links:
                typer.echo(f"  {lnk.source_id} --[{lnk.link_type}]--> {lnk.target_id}")


# ---------------------------------------------------------------------------
# remi onto aggregate <type_name> <metric>
# ---------------------------------------------------------------------------


@cmd.command("aggregate")
def aggregate(
    type_name: str = typer.Argument(..., help="Object type"),
    metric: str = typer.Argument(..., help="Metric: count|sum|avg|min|max"),
    field: str | None = typer.Option(
        None, "--field", help="Field to aggregate on (required for sum/avg/min/max)"
    ),
    filter_: list[str] = typer.Option([], "--filter", "-f", help="Field filters as key=value"),
    group_by: str | None = typer.Option(None, "--group-by", "-g", help="Group results by field"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Compute aggregate metrics across objects."""
    asyncio.run(_aggregate(type_name, metric, field, filter_, group_by, use_json(json_output)))


async def _aggregate(
    type_name: str,
    metric: str,
    field: str | None,
    raw_filters: list[str],
    group_by: str | None,
    fmt_json: bool,
) -> None:
    container = await get_container_async()
    filters = parse_params(raw_filters) if raw_filters else None
    result = await container.knowledge_graph.aggregate(
        type_name,
        metric,
        field,
        filters=filters,
        group_by=group_by,
    )
    if fmt_json:
        json_out(
            {
                "type": type_name,
                "metric": metric,
                "field": field,
                "result": result.model_dump(mode="json"),
            }
        )
    else:
        display = result.value if not result.groups else result.model_dump(mode="json")
        typer.echo(f"{metric}({type_name}.{field or '*'}) = {display}")


# ---------------------------------------------------------------------------
# remi onto timeline <type_name> <object_id>
# ---------------------------------------------------------------------------


@cmd.command("timeline")
def timeline(
    type_name: str = typer.Argument(..., help="Object type"),
    object_id: str = typer.Argument(..., help="Object ID"),
    event_type: list[str] = typer.Option([], "--event-type", "-e", help="Filter by event type"),
    limit: int = typer.Option(50, "--limit", "-l"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Show event history for an object."""
    asyncio.run(_timeline(type_name, object_id, event_type or None, limit, use_json(json_output)))


async def _timeline(
    type_name: str,
    object_id: str,
    event_types: list[str] | None,
    limit: int,
    fmt_json: bool,
) -> None:
    container = await get_container_async()
    events = await container.knowledge_graph.get_timeline(
        type_name,
        object_id,
        event_types=event_types,
        limit=limit,
    )
    if fmt_json:
        json_out(
            {
                "object_type": type_name,
                "object_id": object_id,
                "count": len(events),
                "events": [ev.model_dump(mode="json") for ev in events],
            }
        )
    else:
        typer.echo(f"Timeline for {type_name}/{object_id}: {len(events)} events")
        for ev in events:
            typer.echo(f"  [{ev.timestamp or '?'}] {ev.event_type}: {ev.data}")


# ---------------------------------------------------------------------------
# remi onto schema [type_name]
# ---------------------------------------------------------------------------


@cmd.command("schema")
def schema(
    type_name: str | None = typer.Argument(None, help="Object type (omit to list all)"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Describe object types and their properties."""
    asyncio.run(_schema(type_name, use_json(json_output)))


async def _schema(type_name: str | None, fmt_json: bool) -> None:
    container = await get_container_async()
    if type_name:
        ot = await container.knowledge_graph.get_object_type(type_name)
        if ot is None:
            json_out(
                {"ok": False, "error": f"Unknown type '{type_name}'"}
            ) if fmt_json else typer.echo(f"Unknown type: {type_name}")
            raise typer.Exit(1)
        data = ot.model_dump(mode="json")
        links = await container.knowledge_graph.list_link_types()
        related_links = [
            lnk.model_dump(mode="json")
            for lnk in links
            if lnk.source_type in (type_name, "*") or lnk.target_type in (type_name, "*")
        ]
        data["related_links"] = related_links
        if fmt_json:
            json_out(data)
        else:
            typer.echo(f"\n{ot.name} ({ot.plural_name or ot.name})")
            typer.echo(f"  {ot.description}")
            typer.echo(f"  Provenance: {ot.provenance.value}")
            if ot.properties:
                typer.echo("  Properties:")
                for p in ot.properties:
                    req = " (required)" if p.required else ""
                    typer.echo(f"    {p.name}: {p.data_type}{req}")
    else:
        types = await container.knowledge_graph.list_object_types()
        links = await container.knowledge_graph.list_link_types()
        if fmt_json:
            json_out(
                {
                    "types": [t.model_dump(mode="json") for t in types],
                    "link_types": [lnk.model_dump(mode="json") for lnk in links],
                }
            )
        else:
            typer.echo(f"\nObject Types ({len(types)}):")
            for t in types:
                typer.echo(f"  {t.name:25s} {t.description[:60]}")
            typer.echo(f"\nLink Types ({len(links)}):")
            for lnk in links:
                typer.echo(f"  {lnk.name:20s} {lnk.source_type} -> {lnk.target_type}")


# ---------------------------------------------------------------------------
# remi onto codify <knowledge_type>
# ---------------------------------------------------------------------------


@cmd.command("codify")
def codify(
    knowledge_type: str = typer.Argument(
        ..., help="Knowledge type: observation|policy|causal_link|..."
    ),
    data: list[str] = typer.Option([], "--data", "-d", help="Data fields as key=value"),
    provenance: str = typer.Option("inferred", "--provenance", "-p", help="Provenance tag"),
    source_id: str | None = typer.Option(None, "--source-id", help="Source ID for causal links"),
    target_id: str | None = typer.Option(None, "--target-id", help="Target ID for causal links"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Codify operational knowledge into the ontology."""
    asyncio.run(
        _codify(knowledge_type, data, provenance, source_id, target_id, use_json(json_output))
    )


async def _codify(
    knowledge_type: str,
    raw_data: list[str],
    provenance_str: str,
    source_id: str | None,
    target_id: str | None,
    fmt_json: bool,
) -> None:
    _assert_writable()
    from remi.agent.graph.types import KnowledgeProvenance

    container = await get_container_async()
    data_dict = parse_params(raw_data) if raw_data else {}
    provenance = KnowledgeProvenance(provenance_str)

    entity_id = await container.knowledge_graph.codify(
        knowledge_type,
        data_dict,
        provenance=provenance,
    )

    if source_id and target_id:
        link_type = "CAUSES" if knowledge_type == "causal_link" else "RELATED_TO"
        await container.knowledge_graph.put_link(
            source_id,
            link_type,
            target_id,
            properties={"knowledge_id": entity_id},
        )

    if fmt_json:
        json_out({"ok": True, "entity_id": entity_id, "knowledge_type": knowledge_type})
    else:
        typer.echo(f"Codified {knowledge_type}: {entity_id}")


# ---------------------------------------------------------------------------
# remi onto define <type_name>
# ---------------------------------------------------------------------------


@cmd.command("define")
def define(
    type_name: str = typer.Argument(..., help="New object type name"),
    description: str = typer.Option("", "--description", "-d", help="Type description"),
    property_: list[str] = typer.Option([], "--property", "-p", help="Property defs as name:type"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Define a new object type in the ontology."""
    asyncio.run(_define(type_name, description, property_, use_json(json_output)))


async def _define(
    type_name: str,
    description: str,
    raw_properties: list[str],
    fmt_json: bool,
) -> None:
    _assert_writable()
    from remi.agent.graph.types import KnowledgeProvenance, ObjectTypeDef, PropertyDef

    container = await get_container_async()
    props: list[PropertyDef] = []
    for raw in raw_properties:
        parts = raw.split(":", 1)
        name = parts[0].strip()
        dtype = parts[1].strip() if len(parts) > 1 else "string"
        props.append(PropertyDef(name=name, data_type=dtype))

    type_def = ObjectTypeDef(
        name=type_name,
        description=description,
        properties=tuple(props),
        provenance=KnowledgeProvenance.USER_STATED,
    )
    await container.knowledge_graph.define_object_type(type_def)

    if fmt_json:
        json_out({"ok": True, "type": type_def.model_dump(mode="json")})
    else:
        typer.echo(f"Defined type: {type_name} ({len(props)} properties)")


# ---------------------------------------------------------------------------
# remi onto signals
# ---------------------------------------------------------------------------


@cmd.command("signals")
def signals(
    manager: str | None = typer.Option(None, "--manager", "-m", help="Filter by manager ID"),
    property_id: str | None = typer.Option(None, "--property", "-p", help="Filter by property ID"),
    severity: str | None = typer.Option(None, "--severity", "-s", help="Filter by severity"),
    signal_type: str | None = typer.Option(None, "--type", "-t", help="Filter by signal type"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List active entailed signals across the portfolio."""
    asyncio.run(_signals(manager, property_id, severity, signal_type, use_json(json_output)))


async def _signals(
    manager_id: str | None,
    property_id: str | None,
    severity: str | None,
    signal_type: str | None,
    fmt_json: bool,
) -> None:
    if _http.is_sandbox():
        parts: list[str] = []
        if manager_id:
            parts.append(f"manager_id={manager_id}")
        if property_id:
            parts.append(f"property_id={property_id}")
        if severity:
            parts.append(f"severity={severity}")
        if signal_type:
            parts.append(f"signal_type={signal_type}")
        qs = f"?{'&'.join(parts)}" if parts else ""
        data = _http.get(f"/signals{qs}")
        items = data.get("signals", [])
    else:
        container = await get_container_async()
        _scope: dict[str, str] | None = None
        if manager_id or property_id:
            _scope = {}
            if manager_id:
                _scope["manager_id"] = manager_id
            if property_id:
                _scope["property_id"] = property_id
        sigs = await container.signal_store.list_signals(
            scope=_scope,
            severity=severity,
            signal_type=signal_type,
        )
        items = [
            {
                "signal_id": s.signal_id,
                "signal_type": s.signal_type,
                "severity": s.severity.value,
                "entity_type": s.entity_type,
                "entity_id": s.entity_id,
                "entity_name": s.entity_name,
                "description": s.description,
                "detected_at": s.detected_at.isoformat(),
            }
            for s in sigs
        ]
    if fmt_json:
        json_out({"count": len(items), "signals": items})
    else:
        if not items:
            typer.echo("\nNo active signals.")
            return
        typer.echo(f"\n{len(items)} active signal(s):\n")
        for s in items:
            sev = s["severity"].upper()
            typer.echo(f"  [{sev:8s}] {s['signal_type']:30s} {s['entity_name']}")
            typer.echo(f"             {s['description']}")
            typer.echo(f"             id: {s['signal_id']}")
            typer.echo()


# ---------------------------------------------------------------------------
# remi onto explain <signal-id>
# ---------------------------------------------------------------------------


@cmd.command("explain")
def explain(
    signal_id: str = typer.Argument(..., help="Signal ID to explain"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Show the evidence chain behind a specific signal."""
    asyncio.run(_explain(signal_id, use_json(json_output)))


async def _explain(signal_id: str, fmt_json: bool) -> None:
    if _http.is_sandbox():
        import urllib.error

        try:
            data = _http.get(f"/signals/{signal_id}")
        except urllib.error.HTTPError:
            data = None
        if not data:
            if fmt_json:
                json_out({"ok": False, "error": f"Signal '{signal_id}' not found"})
            else:
                typer.echo(f"Signal not found: {signal_id}")
            raise typer.Exit(1)
        if fmt_json:
            json_out(data)
        else:
            typer.echo(f"\n{data.get('signal_type', '?')} [{data.get('severity', '?').upper()}]")
            ename = data.get("entity_name", "?")
            etype = data.get("entity_type", "?")
            eid = data.get("entity_id", "?")
            typer.echo(f"  Entity: {ename} ({etype}/{eid})")
            typer.echo(f"  {data.get('description', '')}")
            for k, v in data.get("evidence", {}).items():
                typer.echo(f"    {k}: {v}")
        return

    container = await get_container_async()
    signal = await container.signal_store.get_signal(signal_id)
    if signal is None:
        if fmt_json:
            json_out({"ok": False, "error": f"Signal '{signal_id}' not found"})
        else:
            typer.echo(f"Signal not found: {signal_id}")
        raise typer.Exit(1)

    data = {
        "signal_id": signal.signal_id,
        "signal_type": signal.signal_type,
        "severity": signal.severity.value,
        "entity_type": signal.entity_type,
        "entity_id": signal.entity_id,
        "entity_name": signal.entity_name,
        "description": signal.description,
        "provenance": signal.provenance.value,
        "detected_at": signal.detected_at.isoformat(),
        "evidence": signal.evidence,
    }
    if fmt_json:
        json_out(data)
    else:
        typer.echo(f"\n{signal.signal_type} [{signal.severity.value.upper()}]")
        typer.echo(f"  Entity: {signal.entity_name} ({signal.entity_type}/{signal.entity_id})")
        typer.echo(f"  {signal.description}")
        typer.echo(f"  Provenance: {signal.provenance.value}")
        typer.echo("\n  Evidence:")
        for k, v in signal.evidence.items():
            if isinstance(v, list) and len(v) > 3:
                typer.echo(f"    {k}: [{len(v)} items]")
            else:
                typer.echo(f"    {k}: {v}")


# ---------------------------------------------------------------------------
# remi onto infer
# ---------------------------------------------------------------------------


@cmd.command("infer")
def infer(
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Run the full signal pipeline (rule-based + statistical) now."""
    asyncio.run(_infer(use_json(json_output)))


async def _infer(fmt_json: bool) -> None:
    _assert_writable()
    container = await get_container_async()
    result = await container.signal_pipeline.run_all()
    data: dict[str, Any] = {
        "produced": result.produced,
        "signal_count": len(result.signals),
        "sources": {k: v.produced for k, v in result.per_source.items()},
    }
    if result.trace_id:
        data["trace_id"] = result.trace_id
    if fmt_json:
        json_out(data)
    else:
        typer.echo("\nSignal pipeline complete:")
        typer.echo(f"  Signals produced: {result.produced}")
        for source, pr in result.per_source.items():
            typer.echo(f"    {source}: {pr.produced} signals, {pr.errors} errors")
        if result.trace_id:
            typer.echo(f"  Trace:            {result.trace_id}")
            typer.echo(f"                    remi trace show {result.trace_id}")
        if result.signals:
            typer.echo("\n  Active signals:")
            for s in result.signals:
                typer.echo(f"    [{s.severity.value.upper():8s}] {s.signal_type}: {s.entity_name}")
