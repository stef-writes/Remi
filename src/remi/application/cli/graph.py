"""CLI commands for knowledge graph inspection and management.

``remi graph stats``     — entity/edge/annotation counts
``remi graph inspect``   — show entity + 1-hop neighborhood + provenance
``remi graph project``   — re-run the FK projector across all PropertyStore data
``remi graph conflicts`` — list unresolved conflict annotations
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

cmd = typer.Typer(
    name="graph",
    help="Knowledge graph inspection and management.",
    no_args_is_help=True,
)


def _container() -> Any:
    from remi.shell.config.container import Container

    return Container()


@cmd.command()
def stats() -> None:
    """Show entity counts by type, edge counts by link type."""

    async def _run() -> None:
        c = _container()
        await c.ensure_bootstrapped()
        kg = c.knowledge_graph

        object_types = await kg.list_object_types()
        link_types = await kg.list_link_types()

        typer.echo("=== Entity Types ===")
        total_entities = 0
        for ot in object_types:
            objects = await kg.search_objects(ot.name, limit=10_000)
            count = len(objects)
            total_entities += count
            if count > 0:
                typer.echo(f"  {ot.name:<25} {count:>6}")
        typer.echo(f"  {'TOTAL':<25} {total_entities:>6}")

        typer.echo("\n=== Link Types ===")
        for lt in link_types:
            typer.echo(f"  {lt.name:<25} {lt.source_type} -> {lt.target_type}")

    asyncio.run(_run())


@cmd.command()
def inspect(
    entity_type: str = typer.Argument(help="Entity type (e.g. Property, Unit)"),
    entity_id: str = typer.Argument(help="Entity ID"),
    depth: int = typer.Option(1, "--depth", "-d", help="Hop depth for neighborhood"),
) -> None:
    """Show an entity's properties, connected edges, and annotations."""

    async def _run() -> None:
        c = _container()
        await c.ensure_bootstrapped()
        kg = c.knowledge_graph

        obj = await kg.get_object(entity_type, entity_id)
        if obj is None:
            typer.echo(f"Entity not found: {entity_type}/{entity_id}", err=True)
            raise typer.Exit(1)

        typer.echo(f"=== {entity_type}: {entity_id} ===")
        for key, value in obj.properties.items():
            typer.echo(f"  {key}: {value}")

        links = await kg.get_links(entity_id, direction="both")
        if links:
            typer.echo(f"\n=== Edges ({len(links)}) ===")
            for link in links:
                direction = "->" if link.source_id == entity_id else "<-"
                other = link.target_id if link.source_id == entity_id else link.source_id
                typer.echo(f"  {direction} {link.link_type} {other}")

        if depth > 1:
            traversed = await kg.traverse(entity_id, max_depth=depth)
            if traversed:
                typer.echo(f"\n=== Traversal (depth={depth}, {len(traversed)} reachable) ===")
                for t in traversed[:20]:
                    typer.echo(f"  {t.type_name}/{t.id}")

    asyncio.run(_run())


@cmd.command()
def project(
    dry_run: bool = typer.Option(False, "--dry-run", help="Count edges without writing"),
) -> None:
    """Re-run the FK projector across all PropertyStore data."""

    async def _run() -> None:
        c = _container()
        await c.ensure_bootstrapped()
        ps = c.property_store
        projector = c.graph_projector

        entities_by_type: dict[str, list[dict[str, object]]] = {}

        for unit in await ps.list_units():
            entities_by_type.setdefault("Unit", []).append(unit.model_dump(mode="json"))
        for lease in await ps.list_leases():
            entities_by_type.setdefault("Lease", []).append(lease.model_dump(mode="json"))
        for prop in await ps.list_properties():
            entities_by_type.setdefault("Property", []).append(prop.model_dump(mode="json"))
        for mr in await ps.list_maintenance_requests():
            entities_by_type.setdefault("MaintenanceRequest", []).append(mr.model_dump(mode="json"))

        if dry_run:
            total = sum(len(v) for v in entities_by_type.values())
            typer.echo(
                f"Would project edges for {total} entities "
                f"across {len(entities_by_type)} types"
            )
            return

        result = await projector.project_all(entities_by_type)
        typer.echo(
            f"Projection complete: {result.edges_created} edges created, "
            f"{result.edges_skipped} skipped, {result.errors} errors"
        )

    asyncio.run(_run())


@cmd.command()
def conflicts() -> None:
    """List unresolved conflict annotations."""

    async def _run() -> None:
        c = _container()
        await c.ensure_bootstrapped()
        kg = c.knowledge_graph

        annotations = await kg.search_objects("Annotation", limit=1000)
        conflict_annotations = [
            a for a in annotations
            if a.properties.get("annotation_type") == "conflict"
        ]

        if not conflict_annotations:
            typer.echo("No conflicts found.")
            return

        typer.echo(f"=== Conflicts ({len(conflict_annotations)}) ===")
        for ann in conflict_annotations:
            target = ann.properties.get("target_entity_id", "?")
            content = ann.properties.get("content", "")
            typer.echo(f"\n  Entity: {target}")
            typer.echo(f"  {content}")

    asyncio.run(_run())
