"""remi portfolio — browse portfolios and properties."""

from __future__ import annotations

import asyncio

import typer

from remi.application.cli import http as _http
from remi.application.cli.shared import get_container, json_out, use_json

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
        data = _http.get(f"/portfolios{'?manager_id=' + manager_id if manager_id else ''}")
        items = data.get("portfolios", [])
        if fmt_json:
            json_out({"portfolios": items})
        else:
            _render_portfolio_list(items)
        return

    container = get_container()
    result = await container.portfolio_query.list_portfolios(manager_id=manager_id)
    items = [item.model_dump() for item in result]

    if fmt_json:
        json_out({"portfolios": items})
    else:
        _render_portfolio_list(items)


def _render_portfolio_list(items: list[dict[str, object]]) -> None:
    if not items:
        typer.echo("No portfolios found.")
        return
    for p in items:
        typer.echo(
            f"  {str(p['id']):8s}  {str(p['name']):30s}  "
            f"{str(p['manager']):20s}  {p.get('property_count', 0)} properties"
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
            _render_summary(data)
        return

    container = get_container()
    result = await container.portfolio_query.portfolio_summary(portfolio_id)
    if not result:
        json_out({"ok": False, "error": f"Portfolio '{portfolio_id}' not found"})
        raise typer.Exit(1)

    data = result.model_dump()
    if fmt_json:
        json_out(data)
    else:
        _render_summary(data)


def _render_summary(data: dict[str, object]) -> None:
    typer.echo(f"\nPortfolio: {data.get('name', '?')}")
    typer.echo(f"Manager:   {data.get('manager', '?')}")
    props = data.get("properties", [])
    total_props = data.get("total_properties", len(props) if isinstance(props, list) else 0)
    total_units = data.get("total_units", 0)
    occupied = data.get("occupied_units", 0)
    occ_rate = data.get("occupancy_rate", 0)
    revenue = data.get("monthly_revenue", 0)
    typer.echo(f"Properties: {total_props}  |  Units: {total_units}  |  Occupied: {occupied}")
    typer.echo(f"Occupancy:  {occ_rate}%")
    typer.echo(f"Monthly Revenue: ${float(str(revenue)):,.0f}")

    if isinstance(props, list) and props:
        typer.echo("\nProperties:")
        for p in props:
            if not isinstance(p, dict):
                continue
            units = p.get("units", 0)
            occ = p.get("occupied", 0)
            occ_pct = round(int(str(occ)) / int(str(units)) * 100) if units else 0
            typer.echo(
                f"  {str(p.get('id', '')):8s}  {str(p.get('name', '')):30s}  "
                f"{str(p.get('type', '')):12s}  "
                f"{occ}/{units} units ({occ_pct}%)  "
                f"${float(str(p.get('monthly_revenue', 0))):,.0f}/mo"
            )
