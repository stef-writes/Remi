"""remi report — property analytics.

Financial and metrics commands (financial, occupancy, metrics) have been
removed. They will be replaced by DashboardQueryService endpoints.
The rent-analysis command remains as it operates directly on PropertyStore.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import typer

from remi.domain.properties.enums import UnitStatus
from remi.interfaces.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(name="report", help="Property analytics.", no_args_is_help=True)


@cmd.command("rent-analysis")
def rent_analysis(
    property_id: str | None = typer.Option(None, "--property", "-p", help="Property ID (omit for all)"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Compare current rents to market rents, identifying under-priced and over-priced units."""
    asyncio.run(_rent_analysis(property_id, use_json(json_output)))


async def _rent_analysis(property_id: str | None, fmt_json: bool) -> None:
    container = get_container()
    if property_id:
        units = await container.property_store.list_units(property_id=property_id)
    else:
        units = await container.property_store.list_units()

    occupied = [u for u in units if u.status == UnitStatus.OCCUPIED]
    analysis = []
    for u in occupied:
        diff = u.market_rent - u.current_rent
        pct = float(diff / u.market_rent * 100) if u.market_rent else 0
        label = "at_market" if abs(pct) < 3 else ("under_market" if pct > 0 else "over_market")
        analysis.append({
            "unit_id": u.id, "unit_number": u.unit_number, "property_id": u.property_id,
            "current_rent": float(u.current_rent), "market_rent": float(u.market_rent),
            "difference": float(diff), "pct_below_market": round(pct, 1),
            "assessment": label,
        })

    analysis.sort(key=lambda x: x["pct_below_market"], reverse=True)
    total_gap = sum(a["difference"] for a in analysis)
    data = {
        "total_units_analyzed": len(analysis),
        "total_monthly_rent_gap": round(total_gap, 2),
        "under_market": len([a for a in analysis if a["assessment"] == "under_market"]),
        "at_market": len([a for a in analysis if a["assessment"] == "at_market"]),
        "over_market": len([a for a in analysis if a["assessment"] == "over_market"]),
        "details": analysis,
    }

    if fmt_json:
        json_out(data)
    else:
        typer.echo(f"\nRent Analysis ({data['total_units_analyzed']} occupied units)")
        typer.echo(f"  Monthly rent gap: ${data['total_monthly_rent_gap']:,.0f}")
        typer.echo(f"  Under market: {data['under_market']}  |  At market: {data['at_market']}  |  Over: {data['over_market']}")
        typer.echo(f"\n  {'Unit':10s}  {'Current':>9s}  {'Market':>9s}  {'Gap':>8s}  {'%':>6s}  Assessment")
        for a in analysis:
            typer.echo(
                f"  {a['unit_number']:10s}  ${a['current_rent']:>8,.0f}  ${a['market_rent']:>8,.0f}  "
                f"${a['difference']:>7,.0f}  {a['pct_below_market']:>5.1f}%  {a['assessment']}"
            )
