"""remi property — inspect properties and units."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import typer

from remi.domain.properties.enums import LeaseStatus, UnitStatus
from remi.interfaces.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(name="property", help="Inspect properties and units.", no_args_is_help=True)


@cmd.command("list")
def list_properties(
    portfolio_id: str | None = typer.Option(None, "--portfolio", "-p", help="Filter by portfolio ID"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List properties."""
    asyncio.run(_list_properties(portfolio_id, use_json(json_output)))


async def _list_properties(portfolio_id: str | None, fmt_json: bool) -> None:
    container = get_container()
    properties = await container.property_store.list_properties(portfolio_id=portfolio_id)

    items = []
    for p in properties:
        units = await container.property_store.list_units(property_id=p.id)
        occ = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
        items.append({
            "id": p.id, "name": p.name, "address": p.address.one_line(),
            "type": p.property_type.value,
            "units": len(units), "occupied": occ,
        })

    if fmt_json:
        json_out({"properties": items})
    else:
        for p in items:
            occ_pct = round(p["occupied"] / p["units"] * 100) if p["units"] else 0
            typer.echo(f"  {p['id']:8s}  {p['name']:30s}  {p['type']:12s}  {p['occupied']}/{p['units']} ({occ_pct}%)")


@cmd.command("inspect")
def inspect(
    property_id: str = typer.Argument(..., help="Property ID"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Detailed inspection of a property and its units."""
    asyncio.run(_inspect(property_id, use_json(json_output)))


async def _inspect(property_id: str, fmt_json: bool) -> None:
    container = get_container()
    prop = await container.property_store.get_property(property_id)
    if not prop:
        json_out({"ok": False, "error": f"Property '{property_id}' not found"})
        raise typer.Exit(1)

    units = await container.property_store.list_units(property_id=property_id)
    active_leases = await container.property_store.list_leases(
        property_id=property_id, status=LeaseStatus.ACTIVE
    )

    unit_data = []
    for u in units:
        unit_data.append({
            "id": u.id, "number": u.unit_number, "status": u.status.value,
            "bedrooms": u.bedrooms, "bathrooms": u.bathrooms, "sqft": u.sqft,
            "market_rent": float(u.market_rent), "current_rent": float(u.current_rent),
        })

    occupied = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
    vacant = sum(1 for u in units if u.status == UnitStatus.VACANT)
    revenue = sum((u.current_rent for u in units), Decimal("0"))

    data = {
        "property_id": property_id,
        "name": prop.name,
        "address": prop.address.one_line(),
        "type": prop.property_type.value,
        "year_built": prop.year_built,
        "total_units": len(units),
        "occupied": occupied,
        "vacant": vacant,
        "occupancy_rate": round(occupied / len(units) * 100, 1) if units else 0,
        "monthly_revenue": float(revenue),
        "active_leases": len(active_leases),
        "units": unit_data,
    }

    if fmt_json:
        json_out(data)
    else:
        typer.echo(f"\nProperty: {data['name']}")
        typer.echo(f"Address:  {data['address']}")
        typer.echo(f"Type:     {data['type']}  |  Built: {data['year_built'] or '?'}")
        typer.echo(f"Units:    {data['total_units']}  |  Occupied: {occupied}  |  Vacant: {vacant}")
        typer.echo(f"Occupancy: {data['occupancy_rate']}%")
        typer.echo(f"Revenue:   ${data['monthly_revenue']:,.0f}/mo")
        typer.echo("\nUnits:")
        for u in unit_data:
            bed_str = f"{u['bedrooms']}BR" if u['bedrooms'] else "N/A"
            typer.echo(
                f"  {u['number']:10s}  {u['status']:12s}  {bed_str:5s}  "
                f"{u['sqft'] or '?':>5} sqft  "
                f"${u['current_rent']:>8,.0f}  (mkt ${u['market_rent']:>8,.0f})"
            )
