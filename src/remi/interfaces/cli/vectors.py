"""remi vectors — semantic search and embedding index management.

CLI surface for the retrieval layer. Enables human and agent access
to fuzzy, meaning-based lookups across all domain entities.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import typer

from remi.interfaces.cli.shared import get_container_async, json_out, ser, use_json

cmd = typer.Typer(
    name="vectors",
    help="Semantic search and embedding index.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# remi vectors search "query text"
# ---------------------------------------------------------------------------

@cmd.command("search")
def search(
    query: str = typer.Argument(..., help="Natural language search query"),
    entity_type: Optional[str] = typer.Option(
        None, "--type", "-t",
        help="Filter by entity type: Tenant, Unit, Property, MaintenanceRequest",
    ),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
    min_score: float = typer.Option(0.3, "--min-score", "-s", help="Minimum similarity (0-1)"),
    manager_id: Optional[str] = typer.Option(None, "--manager", "-m", help="Filter by manager"),
    property_id: Optional[str] = typer.Option(None, "--property", "-p", help="Filter by property"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Search for entities by meaning, not exact text."""
    asyncio.run(_search(
        query, entity_type, limit, min_score,
        manager_id, property_id, use_json(json_output),
    ))


async def _search(
    query: str,
    entity_type: str | None,
    limit: int,
    min_score: float,
    manager_id: str | None,
    property_id: str | None,
    as_json: bool,
) -> None:
    container = await get_container_async()

    query_vector = await container.embedder.embed_one(query)

    metadata_filter: dict[str, str] | None = None
    if manager_id:
        metadata_filter = {"manager_id": manager_id}
    if property_id:
        metadata_filter = metadata_filter or {}
        metadata_filter["property_id"] = property_id

    results = await container.vector_store.search(
        query_vector,
        limit=limit,
        entity_type=entity_type,
        metadata_filter=metadata_filter,
        min_score=min_score,
    )

    if as_json:
        json_out(ser([
            {
                "entity_id": r.entity_id,
                "entity_type": r.entity_type,
                "score": r.score,
                "text": r.text,
                "source_field": r.record.source_field,
                "metadata": r.record.metadata,
            }
            for r in results
        ]))
        return

    if not results:
        typer.echo("No results found.")
        return

    typer.echo(f"\n  Semantic search: \"{query}\"  ({len(results)} results)\n")
    for i, r in enumerate(results, 1):
        score_pct = f"{r.score * 100:.1f}%"
        typer.echo(f"  {i}. [{r.entity_type}] {r.entity_id}  (score: {score_pct})")
        text_preview = r.text[:120].replace("\n", " ")
        if len(r.text) > 120:
            text_preview += "..."
        typer.echo(f"     {text_preview}")
        typer.echo("")


# ---------------------------------------------------------------------------
# remi vectors stats
# ---------------------------------------------------------------------------

@cmd.command("stats")
def stats(
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Show embedding index statistics."""
    asyncio.run(_stats(use_json(json_output)))


async def _stats(as_json: bool) -> None:
    container = await get_container_async()
    vs = container.vector_store

    total = await vs.count()
    by_type = await vs.stats()

    if as_json:
        json_out({
            "total_embeddings": total,
            "by_entity_type": by_type,
            "embedder_dimension": container.embedder.dimension,
        })
        return

    typer.echo(f"\n  Vector Index Stats")
    typer.echo(f"  {'─' * 40}")
    typer.echo(f"  Total embeddings:   {total}")
    typer.echo(f"  Embedder dimension: {container.embedder.dimension}")
    if by_type:
        typer.echo(f"\n  By entity type:")
        for etype, count in sorted(by_type.items()):
            typer.echo(f"    {etype:25s} {count:>6}")
    else:
        typer.echo("  (index is empty)")
    typer.echo("")


# ---------------------------------------------------------------------------
# remi vectors embed
# ---------------------------------------------------------------------------

@cmd.command("embed")
def embed(
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Run the embedding pipeline over all domain entities."""
    asyncio.run(_embed(use_json(json_output)))


async def _embed(as_json: bool) -> None:
    container = await get_container_async()
    result = await container.embedding_pipeline.run_full()

    if as_json:
        json_out({
            "embedded": result.embedded,
            "skipped": result.skipped,
            "errors": result.errors,
            "by_type": result.by_type,
        })
        return

    typer.echo(f"\n  Embedding pipeline complete")
    typer.echo(f"  {'─' * 40}")
    typer.echo(f"  Embedded:  {result.embedded}")
    typer.echo(f"  Skipped:   {result.skipped}")
    typer.echo(f"  Errors:    {result.errors}")
    if result.by_type:
        typer.echo(f"\n  By entity type:")
        for etype, count in sorted(result.by_type.items()):
            typer.echo(f"    {etype:25s} {count:>6}")
    typer.echo("")
