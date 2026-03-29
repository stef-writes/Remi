"""remi units — search and filter units."""

from __future__ import annotations

import asyncio

import typer

from remi.domain.properties.enums import UnitStatus
from remi.interfaces.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(name="units", help="Search and filter units.", no_args_is_help=True)


@cmd.command("list")
def list_units(
    property_id: str | None = typer.Option(None, "--property", "-p", help="Filter by property ID"),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status: vacant, occupied, maintenance"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List units across all properties."""
    asyncio.run(_list_units(property_id, status, use_json(json_output)))


async def _list_units(property_id: str | None, status_str: str | None, fmt_json: bool) -> None:
    container = get_container()
    status = UnitStatus(status_str) if status_str else None
    units = await container.property_store.list_units(property_id=property_id, status=status)

    items = []
    for u in units:
        prop = await container.property_store.get_property(u.property_id)
        items.append({
            "id": u.id, "unit_number": u.unit_number,
            "property": prop.name if prop else u.property_id,
            "status": u.status.value,
            "bedrooms": u.bedrooms, "sqft": u.sqft,
            "market_rent": float(u.market_rent), "current_rent": float(u.current_rent),
        })

    if fmt_json:
        json_out({"count": len(items), "units": items})
    else:
        typer.echo(f"\n{len(items)} units found:\n")
        for u in items:
            bed_str = f"{u['bedrooms']}BR" if u['bedrooms'] else "N/A"
            typer.echo(
                f"  {u['id']:12s}  {u['property']:30s}  {u['unit_number']:10s}  "
                f"{u['status']:12s}  {bed_str:5s}  ${u['market_rent']:>8,.0f}"
            )
