"""remi portfolio — browse portfolios and properties."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import typer

from remi.cli import http as _http
from remi.cli.shared import get_container, json_out, use_json
from remi.models.properties import UnitStatus

cmd = typer.Typer(name="portfolio", help="Browse portfolios and properties.", no_args_is_help=True)


@cmd.command("list")
def list_portfolios(
    manager_id: str | None = typer.Option(None, "--manager", "-m", help="Filter by manager ID"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List all portfolios."""
    asyncio.run(_list_portfolios(manager_id, use_json(json_output)))


async def _list_portfolios(manager_id: str | None, fmt_json: bool) -> None:
    if _http.is_sandbox():
        qs = f"?manager_id={manager_id}" if manager_id else ""
        data = _http.get(f"/portfolios{qs}")
        items = data.get("portfolios", [])
    else:
        container = get_container()
        portfolios = await container.property_store.list_portfolios(manager_id=manager_id)
        items = []
        for p in portfolios:
            manager = await container.property_store.get_manager(p.manager_id)
            props = await container.property_store.list_properties(portfolio_id=p.id)
            items.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "manager": manager.name if manager else "?",
                    "properties": len(props),
                    "description": p.description,
                }
            )

    if fmt_json:
        json_out({"portfolios": items})
    else:
        if not items:
            typer.echo("No portfolios found.")
            return
        for p in items:
            typer.echo(
                f"  {p['id']:8s}  {p['name']:30s}  {p['manager']:20s}  {p['properties']} properties"
            )


@cmd.command("summary")
def summary(
    portfolio_id: str = typer.Argument(..., help="Portfolio ID"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Show a portfolio summary with key metrics."""
    asyncio.run(_summary(portfolio_id, use_json(json_output)))


async def _summary(portfolio_id: str, fmt_json: bool) -> None:
    if _http.is_sandbox():
        data = _http.get(f"/portfolios/{portfolio_id}/summary")
        if not data or data.get("error"):
            json_out(
                {"ok": False, "error": data.get("error", f"Portfolio '{portfolio_id}' not found")}
            )
            raise typer.Exit(1)
        if fmt_json:
            json_out(data)
        else:
            typer.echo(f"\nPortfolio: {data.get('name', '?')}")
            typer.echo(f"Manager:   {data.get('manager', '?')}")
            typer.echo(f"Properties: {data.get('total_properties', 0)}")
            typer.echo(f"Occupancy:  {data.get('occupancy_rate', 0)}%")
            typer.echo(f"Monthly Revenue: ${data.get('monthly_revenue', 0):,.0f}")
        return

    container = get_container()
    portfolio = await container.property_store.get_portfolio(portfolio_id)
    if not portfolio:
        json_out({"ok": False, "error": f"Portfolio '{portfolio_id}' not found"})
        raise typer.Exit(1)

    manager = await container.property_store.get_manager(portfolio.manager_id)
    properties = await container.property_store.list_properties(portfolio_id=portfolio_id)

    total_units = 0
    occupied = 0
    total_revenue = Decimal("0")

    prop_details = []
    for prop in properties:
        units = await container.property_store.list_units(property_id=prop.id)
        occ = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
        rev = sum((u.current_rent for u in units), Decimal("0"))
        total_units += len(units)
        occupied += occ
        total_revenue += rev
        prop_details.append(
            {
                "id": prop.id,
                "name": prop.name,
                "type": prop.property_type.value,
                "units": len(units),
                "occupied": occ,
                "monthly_revenue": float(rev),
            }
        )

    data = {
        "portfolio_id": portfolio_id,
        "name": portfolio.name,
        "manager": manager.name if manager else "Unknown",
        "description": portfolio.description,
        "total_properties": len(properties),
        "total_units": total_units,
        "occupied_units": occupied,
        "occupancy_rate": round(occupied / total_units * 100, 1) if total_units else 0,
        "monthly_revenue": float(total_revenue),
        "properties": prop_details,
    }

    if fmt_json:
        json_out(data)
    else:
        typer.echo(f"\nPortfolio: {data['name']}")
        typer.echo(f"Manager:   {data['manager']}")
        typer.echo(
            f"Properties: {data['total_properties']}  |  "
            f"Units: {data['total_units']}  |  "
            f"Occupied: {data['occupied_units']}"
        )
        typer.echo(f"Occupancy:  {data['occupancy_rate']}%")
        typer.echo(f"Monthly Revenue: ${data['monthly_revenue']:,.0f}")
        typer.echo("\nProperties:")
        for p in prop_details:
            occ_pct = round(p["occupied"] / p["units"] * 100) if p["units"] else 0
            typer.echo(
                f"  {p['id']:8s}  {p['name']:30s}  {p['type']:12s}  "
                f"{p['occupied']}/{p['units']} units ({occ_pct}%)  "
                f"${p['monthly_revenue']:,.0f}/mo"
            )
