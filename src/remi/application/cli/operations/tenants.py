"""remi tenants — tenant lookup and lease history."""

from __future__ import annotations

import asyncio

import typer

from remi.application.cli import http as _http
from remi.application.cli.shared import get_container, json_out, ser, use_json

cmd = typer.Typer(name="tenants", help="Tenant lookup and lease history.", no_args_is_help=True)


@cmd.command("lookup")
def lookup(
    tenant_id: str = typer.Argument(..., help="Tenant ID"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Get tenant details and lease history."""
    asyncio.run(_lookup(tenant_id, use_json(json_output)))


async def _lookup(tenant_id: str, fmt_json: bool) -> None:
    if _http.is_sandbox():
        data = _http.get(f"/tenants/{tenant_id}")
        if not data or data.get("error"):
            json_out({"ok": False, "error": data.get("error", f"Tenant '{tenant_id}' not found")})
            raise typer.Exit(1)
    else:
        container = get_container()
        detail = await container.tenant_resolver.get_tenant_detail(tenant_id)
        if not detail:
            json_out({"ok": False, "error": f"Tenant '{tenant_id}' not found"})
            raise typer.Exit(1)
        data = ser(detail.model_dump())

    if fmt_json:
        json_out(data)
    else:
        typer.echo(f"\nTenant: {data['name']}")
        typer.echo(f"Email:  {data.get('email') or 'N/A'}")
        typer.echo(f"Phone:  {data.get('phone') or 'N/A'}")
        leases = data.get("leases", [])
        typer.echo(f"\nLeases ({len(leases)}):")
        for le in leases:
            typer.echo(
                f"  {le['lease_id']:10s}  Unit {le['unit']:8s}  {le['status']:10s}  "
                f"${le['monthly_rent']:>8,.0f}/mo  {le['start']} to {le['end']}"
            )
