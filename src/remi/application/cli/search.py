"""remi search — hybrid keyword + semantic entity search.

CLI surface for the portfolio search service. Returns managers, properties,
tenants, units, and maintenance requests matching a query.
"""

from __future__ import annotations

import asyncio

import typer

from remi.application.cli.shared import get_container_async, json_out, ser, use_json

cmd = typer.Typer(
    name="search",
    help="Portfolio-wide entity search (keyword + semantic).",
    no_args_is_help=True,
)


@cmd.command("query")
def query(
    query: str = typer.Argument(..., help="Search query — name, address, or description"),
    types: str | None = typer.Option(
        None,
        "--types",
        "-t",
        help="Comma-separated entity types: PropertyManager,Property,"
        "Tenant,Unit,MaintenanceRequest,DocumentRow",
    ),
    manager_id: str | None = typer.Option(None, "--manager", "-m", help="Scope to a manager"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Search for entities by name, address, or meaning."""
    asyncio.run(_query(query, types, manager_id, limit, use_json(json_output)))


async def _query(
    query: str,
    types_raw: str | None,
    manager_id: str | None,
    limit: int,
    as_json: bool,
) -> None:
    container = await get_container_async()
    svc = container.search_service

    type_list: list[str] | None = None
    if types_raw:
        type_list = [t.strip() for t in types_raw.split(",") if t.strip()]

    results = await svc.search(query, types=type_list, manager_id=manager_id, limit=limit)

    if as_json:
        json_out(
            ser(
                [
                    {
                        "entity_id": h.entity_id,
                        "entity_type": h.entity_type,
                        "label": h.label,
                        "title": h.title,
                        "subtitle": h.subtitle,
                        "score": h.score,
                        "metadata": h.metadata,
                    }
                    for h in results
                ]
            )
        )
        return

    if not results:
        typer.echo("No results found.")
        return

    typer.echo(f'\n  Search: "{query}"  ({len(results)} results)\n')
    for i, h in enumerate(results, 1):
        score_pct = f"{h.score * 100:.1f}%"
        typer.echo(f"  {i}. [{h.label}] {h.title}  (score: {score_pct})")
        if h.subtitle:
            typer.echo(f"     {h.subtitle}")
        typer.echo(f"     id: {h.entity_id}")
        typer.echo("")
