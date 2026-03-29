"""remi kb — query the knowledge graph."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from remi.interfaces.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(name="kb", help="Query the knowledge graph.", no_args_is_help=True)


def _get_namespaces(kb: Any) -> list[str]:
    """Extract known namespaces from the in-memory knowledge store."""
    if hasattr(kb, "_entities"):
        return list(kb._entities.keys())
    return ["default"]


@cmd.command("search")
def search(
    entity_type: str | None = typer.Option(None, "--type", "-t", help="Filter by entity type"),
    query: str | None = typer.Option(None, "--query", "-q", help="Text search in entity properties"),
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Specific namespace"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Search the knowledge base for entities by type and/or text query."""
    asyncio.run(_search(entity_type, query, namespace, limit, use_json(json_output)))


async def _search(
    entity_type: str | None,
    query: str | None,
    namespace: str | None,
    limit: int,
    fmt_json: bool,
) -> None:
    container = get_container()
    kb = container.knowledge_store

    if namespace:
        entities = await kb.find_entities(namespace, entity_type=entity_type, query=query, limit=limit)
    else:
        all_ns = _get_namespaces(kb)
        entities = []
        for ns in all_ns:
            found = await kb.find_entities(ns, entity_type=entity_type, query=query, limit=limit)
            entities.extend(found)
            if len(entities) >= limit:
                break
        entities = entities[:limit]

    items = [
        {"id": e.entity_id, "type": e.entity_type, "namespace": e.namespace, "properties": e.properties}
        for e in entities
    ]

    if fmt_json:
        json_out({"count": len(items), "entities": items})
    else:
        typer.echo(f"\n{len(items)} entities found:\n")
        for e in items:
            typer.echo(f"  {e['id']:30s}  {e['type']:15s}  ns={e['namespace']}")


@cmd.command("related")
def related(
    entity_id: str = typer.Argument(..., help="Entity ID to start from"),
    relation_type: str | None = typer.Option(None, "--relation-type", "-r", help="Filter by relationship type"),
    direction: str = typer.Option("both", "--direction", "-d", help="outgoing, incoming, or both"),
    max_depth: int = typer.Option(2, "--max-depth", help="Max traversal depth"),
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Specific namespace"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Find entities related to a given entity via the knowledge graph."""
    asyncio.run(_related(entity_id, relation_type, direction, max_depth, namespace, use_json(json_output)))


async def _related(
    entity_id: str,
    relation_type: str | None,
    direction: str,
    max_depth: int,
    namespace: str | None,
    fmt_json: bool,
) -> None:
    container = get_container()
    kb = container.knowledge_store
    namespaces = [namespace] if namespace else _get_namespaces(kb)

    all_rels: list[dict[str, Any]] = []
    all_traversed: list[dict[str, Any]] = []

    for ns in namespaces:
        rels = await kb.get_relationships(ns, entity_id, relation_type=relation_type, direction=direction)
        for r in rels:
            all_rels.append({"source": r.source_id, "target": r.target_id, "type": r.relation_type, "namespace": ns})

        if max_depth > 1:
            traversed = await kb.traverse(
                ns, entity_id,
                relation_types=[relation_type] if relation_type else None,
                max_depth=max_depth,
            )
            for e in traversed:
                all_traversed.append({
                    "id": e.entity_id, "type": e.entity_type,
                    "namespace": e.namespace, "properties": e.properties,
                })

    data = {
        "entity_id": entity_id,
        "direct_relationships": all_rels,
        "related_entities": all_traversed,
    }

    if fmt_json:
        json_out(data)
    else:
        typer.echo(f"\nRelationships for {entity_id}:")
        typer.echo(f"  Direct: {len(all_rels)}")
        for r in all_rels:
            typer.echo(f"    {r['source']} --[{r['type']}]--> {r['target']}")
        typer.echo(f"  Related entities: {len(all_traversed)}")
        for e in all_traversed:
            typer.echo(f"    {e['id']:30s}  {e['type']:15s}")


@cmd.command("summary")
def summary(
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Specific namespace"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """High-level summary of the knowledge base: entity counts by type."""
    asyncio.run(_summary(namespace, use_json(json_output)))


async def _summary(namespace: str | None, fmt_json: bool) -> None:
    container = get_container()
    kb = container.knowledge_store
    namespaces = [namespace] if namespace else _get_namespaces(kb)

    type_counts: dict[str, int] = {}
    total_entities = 0

    for ns in namespaces:
        for etype in ("document", "property", "tenant", "unit", "lease", "financial", "maintenance"):
            entities = await kb.find_entities(ns, entity_type=etype)
            if entities:
                type_counts[etype] = type_counts.get(etype, 0) + len(entities)
                total_entities += len(entities)

    data = {
        "namespaces": len(namespaces),
        "total_entities": total_entities,
        "by_type": type_counts,
    }

    if fmt_json:
        json_out(data)
    else:
        typer.echo(f"\nKnowledge Base Summary")
        typer.echo(f"  Namespaces: {data['namespaces']}")
        typer.echo(f"  Total entities: {total_entities}")
        if type_counts:
            typer.echo(f"\n  By type:")
            for t, c in sorted(type_counts.items()):
                typer.echo(f"    {t:15s}  {c}")
        else:
            typer.echo("  (empty)")
