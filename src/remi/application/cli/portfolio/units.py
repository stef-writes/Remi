"""remi units — search and filter units."""

from __future__ import annotations

import asyncio

import typer

from remi.application.cli import http as _http
from remi.application.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(name="units", help="Search and filter units.", no_args_is_help=True)


@cmd.command("list")
def list_units(
    property_id: str | None = typer.Option(None, "--property", "-p", help="Filter by property ID"),
    status: str | None = typer.Option(
        None, "--status", "-s", help="Filter by status: vacant, occupied, maintenance"
    ),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List units across all properties."""
    asyncio.run(_list_units(property_id, status, use_json(json_output)))


async def _list_units(property_id: str | None, status_str: str | None, fmt_json: bool) -> None:
    if _http.is_sandbox():
        parts: list[str] = []
        if property_id:
            parts.append(f"property_id={property_id}")
        if status_str:
            parts.append(f"status={status_str}")
        qs = f"?{'&'.join(parts)}" if parts else ""
        data = _http.get(f"/units{qs}")
        items = data.get("units", [])
    else:
        container = get_container()
        result = await container.unit_resolver.list_units(
            property_id=property_id, status=status_str,
        )
        items = [item.model_dump() for item in result.units]

    if fmt_json:
        json_out({"count": len(items), "units": items})
    else:
        typer.echo(f"\n{len(items)} units found:\n")
        for u in items:
            bed_str = f"{u['bedrooms']}BR" if u.get("bedrooms") else "N/A"
            prop_name = u.get("property_name", u.get("property", ""))
            typer.echo(
                f"  {u['id']:12s}  {prop_name:30s}  {u['unit_number']:10s}  "
                f"{u['status']:12s}  {bed_str:5s}  ${u['market_rent']:>8,.0f}"
            )
