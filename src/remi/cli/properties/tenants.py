"""remi tenants — tenant lookup and lease history."""

from __future__ import annotations

import asyncio

import typer

from remi.cli import http as _http
from remi.cli.shared import get_container, json_out, ser, use_json

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
        tenant = await container.property_store.get_tenant(tenant_id)
        if not tenant:
            json_out({"ok": False, "error": f"Tenant '{tenant_id}' not found"})
            raise typer.Exit(1)

        leases = await container.property_store.list_leases(tenant_id=tenant_id)
        lease_info = []
        for le in leases:
            unit = await container.property_store.get_unit(le.unit_id)
            lease_info.append(
                {
                    "lease_id": le.id,
                    "unit": unit.unit_number if unit else le.unit_id,
                    "property_id": le.property_id,
                    "start": le.start_date.isoformat(),
                    "end": le.end_date.isoformat(),
                    "monthly_rent": float(le.monthly_rent),
                    "status": le.status.value,
                }
            )

        data = ser(
            {
                "tenant_id": tenant_id,
                "name": tenant.name,
                "email": tenant.email,
                "phone": tenant.phone,
                "leases": lease_info,
            }
        )

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
