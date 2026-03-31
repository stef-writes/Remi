"""remi maintenance — maintenance request dashboard."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import typer

from remi.cli import http as _http
from remi.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(name="maintenance", help="Maintenance request dashboard.", no_args_is_help=True)


@cmd.command("list")
def list_requests(
    property_id: str | None = typer.Option(None, "--property", "-p"),
    status: str | None = typer.Option(
        None, "--status", "-s", help="open, in_progress, completed, cancelled"
    ),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List maintenance requests."""
    asyncio.run(_list_requests(property_id, status, use_json(json_output)))


async def _list_requests(property_id: str | None, status_str: str | None, fmt_json: bool) -> None:
    if _http.is_sandbox():
        parts: list[str] = []
        if property_id:
            parts.append(f"property_id={property_id}")
        if status_str:
            parts.append(f"status={status_str}")
        qs = f"?{'&'.join(parts)}" if parts else ""
        data = _http.get(f"/maintenance{qs}")
        items = data.get("requests", [])
    else:
        from remi.models.properties import MaintenanceStatus

        container = get_container()
        status = MaintenanceStatus(status_str) if status_str else None
        requests = await container.property_store.list_maintenance_requests(
            property_id=property_id, status=status
        )
        requests.sort(key=lambda r: r.created_at, reverse=True)
        items = []
        for r in requests:
            items.append(
                {
                    "id": r.id,
                    "property_id": r.property_id,
                    "unit_id": r.unit_id,
                    "title": r.title,
                    "category": r.category.value,
                    "priority": r.priority.value,
                    "status": r.status.value,
                    "cost": float(r.cost) if r.cost else None,
                    "created": r.created_at.isoformat(),
                }
            )

    if fmt_json:
        json_out({"count": len(items), "requests": items})
    else:
        typer.echo(f"\n{len(items)} maintenance requests:\n")
        for r in items:
            cost_str = f"${r['cost']:>8,.0f}" if r["cost"] else "      N/A"
            typer.echo(
                f"  {r['id']:10s}  {r['priority']:10s}  {r['status']:12s}  "
                f"{r['category']:12s}  {cost_str}  {r['title']}"
            )


@cmd.command("summary")
def summary(
    property_id: str | None = typer.Option(None, "--property", "-p"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Maintenance summary with counts by status, category, and cost totals."""
    asyncio.run(_summary(property_id, use_json(json_output)))


async def _summary(property_id: str | None, fmt_json: bool) -> None:
    if _http.is_sandbox():
        qs = f"?property_id={property_id}" if property_id else ""
        data = _http.get(f"/maintenance/summary{qs}")
        if fmt_json:
            json_out(data)
        else:
            typer.echo(f"\nMaintenance Summary ({data.get('total', 0)} total requests)")
            typer.echo(f"Total Cost: ${data.get('total_cost', 0):,.0f}")
            for s, c in sorted(data.get("by_status", {}).items()):
                typer.echo(f"  {s:15s}  {c}")
        return

    container = get_container()
    requests = await container.property_store.list_maintenance_requests(property_id=property_id)

    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    total_cost = Decimal("0")

    for r in requests:
        by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        by_category[r.category.value] = by_category.get(r.category.value, 0) + 1
        if r.cost:
            total_cost += r.cost

    data = {
        "total": len(requests),
        "by_status": by_status,
        "by_category": by_category,
        "total_cost": float(total_cost),
    }

    if fmt_json:
        json_out(data)
    else:
        typer.echo(f"\nMaintenance Summary ({len(requests)} total requests)")
        typer.echo(f"Total Cost: ${float(total_cost):,.0f}")
        typer.echo("\nBy Status:")
        for s, c in sorted(by_status.items()):
            typer.echo(f"  {s:15s}  {c}")
        typer.echo("\nBy Category:")
        for cat, c in sorted(by_category.items()):
            typer.echo(f"  {cat:15s}  {c}")
