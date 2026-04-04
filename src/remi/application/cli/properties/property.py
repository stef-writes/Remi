"""remi property — inspect properties and units."""

from __future__ import annotations

import asyncio

import typer

from remi.application.cli import http as _http
from remi.application.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(name="property", help="Inspect properties and units.", no_args_is_help=True)


@cmd.command("list")
def list_properties(
    portfolio_id: str | None = typer.Option(
        None, "--portfolio", "-p", help="Filter by portfolio ID"
    ),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List properties."""
    asyncio.run(_list_properties(portfolio_id, use_json(json_output)))


async def _list_properties(portfolio_id: str | None, fmt_json: bool) -> None:
    if _http.is_sandbox():
        qs = f"?portfolio_id={portfolio_id}" if portfolio_id else ""
        data = _http.get(f"/properties{qs}")
        items = data.get("properties", [])
    else:
        container = get_container()
        result = await container.property_query.list_properties(portfolio_id=portfolio_id)
        items = [item.model_dump() for item in result]

    if fmt_json:
        json_out({"properties": items})
    else:
        _render_property_list(items)


def _render_property_list(items: list[dict[str, object]]) -> None:
    for p in items:
        units = int(str(p.get("total_units", p.get("units", 0))))
        occ = int(str(p.get("occupied", 0)))
        occ_pct = round(occ / units * 100) if units else 0
        typer.echo(
            f"  {str(p.get('id', '')):8s}  {str(p.get('name', '')):30s}  "
            f"{str(p.get('type', '')):12s}  "
            f"{occ}/{units} ({occ_pct}%)"
        )


@cmd.command("inspect")
def inspect(
    property_id: str = typer.Argument(..., help="Property ID"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Detailed inspection of a property and its units."""
    asyncio.run(_inspect(property_id, use_json(json_output)))


async def _inspect(property_id: str, fmt_json: bool) -> None:
    if _http.is_sandbox():
        data = _http.get(f"/properties/{property_id}")
        if not data or data.get("error"):
            json_out(
                {"ok": False, "error": data.get("error", f"Property '{property_id}' not found")}
            )
            raise typer.Exit(1)
        if fmt_json:
            json_out(data)
        else:
            _render_property_detail(data)
        return

    container = get_container()
    detail = await container.property_query.get_property_detail(property_id)
    if not detail:
        json_out({"ok": False, "error": f"Property '{property_id}' not found"})
        raise typer.Exit(1)

    data = detail.model_dump()
    if fmt_json:
        json_out(data)
    else:
        _render_property_detail(data)


def _render_property_detail(data: dict[str, object]) -> None:
    address = data.get("address", "")
    if isinstance(address, dict):
        parts = (address.get("street", ""), address.get("city", ""),
                 address.get("state", ""), address.get("zip_code", ""))
        address = f"{parts[0]}, {parts[1]}, {parts[2]} {parts[3]}"

    typer.echo(f"\nProperty: {data.get('name', '?')}")
    typer.echo(f"Address:  {address}")
    prop_type = data.get("property_type", data.get("type", "?"))
    typer.echo(f"Type:     {prop_type}  |  Built: {data.get('year_built') or '?'}")

    total = data.get("total_units", 0)
    occupied = data.get("occupied", 0)
    vacant = data.get("vacant", 0)
    typer.echo(f"Units:    {total}  |  Occupied: {occupied}  |  Vacant: {vacant}")
    typer.echo(f"Occupancy: {data.get('occupancy_rate', 0)}%")
    typer.echo(f"Revenue:   ${float(str(data.get('monthly_revenue', 0))):,.0f}/mo")

    units = data.get("units", [])
    if isinstance(units, list) and units:
        typer.echo("\nUnits:")
        for u in units:
            if not isinstance(u, dict):
                continue
            bed = u.get("bedrooms")
            bed_str = f"{bed}BR" if bed else "N/A"
            sqft = u.get("sqft") or "?"
            current = float(str(u.get("current_rent", 0)))
            market = float(str(u.get("market_rent", 0)))
            typer.echo(
                f"  {str(u.get('unit_number', u.get('number', ''))):10s}  "
                f"{str(u.get('status', '')):12s}  {bed_str:5s}  "
                f"{sqft:>5} sqft  "
                f"${current:>8,.0f}  (mkt ${market:>8,.0f})"
            )
