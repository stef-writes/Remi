"""remi leases — lease management and expiration tracking."""

from __future__ import annotations

import asyncio

import typer

from remi.application.cli import http as _http
from remi.application.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(
    name="leases", help="Lease management and expiration tracking.", no_args_is_help=True
)


@cmd.command("expiring")
def expiring(
    days: int = typer.Option(60, "--days", "-d", help="Days to look ahead"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Find leases expiring within N days."""
    asyncio.run(_expiring(days, use_json(json_output)))


async def _expiring(days: int, fmt_json: bool) -> None:
    if _http.is_sandbox():
        data = _http.get(f"/leases/expiring?days={days}")
        items = data.get("leases", [])
    else:
        container = get_container()
        result = await container.lease_resolver.expiring_leases(days=days)
        items = [item.model_dump() for item in result.leases]

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
    status: str | None = typer.Option(
        None, "--status", "-s", help="active, expired, terminated, pending"
    ),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List leases with optional filters."""
    asyncio.run(_list_leases(property_id, status, use_json(json_output)))


async def _list_leases(property_id: str | None, status_str: str | None, fmt_json: bool) -> None:
    if _http.is_sandbox():
        parts: list[str] = []
        if property_id:
            parts.append(f"property_id={property_id}")
        if status_str:
            parts.append(f"status={status_str}")
        qs = f"?{'&'.join(parts)}" if parts else ""
        data = _http.get(f"/leases{qs}")
        items = data.get("leases", [])
    else:
        container = get_container()
        result = await container.lease_resolver.list_leases(
            property_id=property_id, status=status_str,
        )
        items = [item.model_dump() for item in result.leases]

    if fmt_json:
        json_out({"count": len(items), "leases": items})
    else:
        typer.echo(f"\n{len(items)} leases:\n")
        for le in items:
            typer.echo(
                f"  {le['id']:10s}  {le['tenant']:25s}  {le['status']:10s}  "
                f"${le['rent']:>8,.0f}/mo  {le['start']} to {le['end']}"
            )
