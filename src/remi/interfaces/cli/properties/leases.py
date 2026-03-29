"""remi leases — lease management and expiration tracking."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import typer

from remi.domain.properties.enums import LeaseStatus
from remi.interfaces.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(name="leases", help="Lease management and expiration tracking.", no_args_is_help=True)


@cmd.command("expiring")
def expiring(
    days: int = typer.Option(60, "--days", "-d", help="Days to look ahead"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Find leases expiring within N days."""
    asyncio.run(_expiring(days, use_json(json_output)))


async def _expiring(days: int, fmt_json: bool) -> None:
    container = get_container()
    today = date.today()
    deadline = today + timedelta(days=days)

    leases = await container.property_store.list_leases(status=LeaseStatus.ACTIVE)
    expiring = [le for le in leases if le.end_date <= deadline]
    expiring.sort(key=lambda le: le.end_date)

    items = []
    for le in expiring:
        tenant = await container.property_store.get_tenant(le.tenant_id)
        unit = await container.property_store.get_unit(le.unit_id)
        prop = await container.property_store.get_property(le.property_id)
        items.append({
            "lease_id": le.id,
            "tenant": tenant.name if tenant else le.tenant_id,
            "unit": unit.unit_number if unit else le.unit_id,
            "property": prop.name if prop else le.property_id,
            "monthly_rent": float(le.monthly_rent),
            "end_date": le.end_date.isoformat(),
            "days_left": (le.end_date - today).days,
        })

    if fmt_json:
        json_out({"days_window": days, "expiring_count": len(items), "leases": items})
    else:
        typer.echo(f"\nLeases expiring within {days} days: {len(items)}\n")
        if not items:
            typer.echo("  None.")
            return
        for le in items:
            typer.echo(
                f"  {le['lease_id']:10s}  {le['tenant']:25s}  {le['property']:25s}  "
                f"Unit {le['unit']:8s}  ${le['monthly_rent']:>8,.0f}/mo  "
                f"Expires: {le['end_date']}  ({le['days_left']}d)"
            )


@cmd.command("list")
def list_leases(
    property_id: str | None = typer.Option(None, "--property", "-p"),
    status: str | None = typer.Option(None, "--status", "-s", help="active, expired, terminated, pending"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List leases with optional filters."""
    asyncio.run(_list_leases(property_id, status, use_json(json_output)))


async def _list_leases(property_id: str | None, status_str: str | None, fmt_json: bool) -> None:
    container = get_container()
    status = LeaseStatus(status_str) if status_str else None
    leases = await container.property_store.list_leases(property_id=property_id, status=status)

    items = []
    for le in leases:
        tenant = await container.property_store.get_tenant(le.tenant_id)
        items.append({
            "id": le.id, "tenant": tenant.name if tenant else le.tenant_id,
            "unit_id": le.unit_id, "property_id": le.property_id,
            "start": le.start_date.isoformat(), "end": le.end_date.isoformat(),
            "rent": float(le.monthly_rent), "status": le.status.value,
        })

    if fmt_json:
        json_out({"count": len(items), "leases": items})
    else:
        typer.echo(f"\n{len(items)} leases:\n")
        for le in items:
            typer.echo(
                f"  {le['id']:10s}  {le['tenant']:25s}  {le['status']:10s}  "
                f"${le['rent']:>8,.0f}/mo  {le['start']} to {le['end']}"
            )
