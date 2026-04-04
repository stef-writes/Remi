"""remi managers — create, review, assign, and merge property managers."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from remi.application.cli import http as _http
from remi.application.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(name="managers", help="Manage property managers.", no_args_is_help=True)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@cmd.command("list")
def list_managers(
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List all managers with portfolio metrics."""
    asyncio.run(_list_managers(use_json(json_output)))


async def _list_managers(fmt_json: bool) -> None:
    if _http.is_sandbox():
        data = _http.get("/managers")
        items = data.get("managers", [])
        if fmt_json:
            json_out({"managers": items})
        else:
            _render_manager_list(items)
        return

    container = get_container()
    summaries = await container.manager_review.list_manager_summaries()
    items = [s.model_dump() for s in summaries]
    if fmt_json:
        json_out({"managers": items})
    else:
        _render_manager_list(items)


def _render_manager_list(items: list[dict[str, Any]]) -> None:
    if not items:
        typer.echo("No managers found.")
        return
    typer.echo(f"  {'ID':30s}  {'Name':25s}  {'Properties':>10}  {'Units':>6}  {'Occupancy':>10}")
    typer.echo("  " + "-" * 90)
    for m in items:
        occ = m.get("occupancy_rate", 0)
        typer.echo(
            f"  {str(m['id']):30s}  {str(m['name']):25s}"
            f"  {m.get('property_count', 0):>10}  {m.get('total_units', 0):>6}"
            f"  {float(str(occ)):>9.1f}%"
        )


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@cmd.command("create")
def create_manager(
    name: str = typer.Argument(..., help="Manager full name"),
    email: str = typer.Option("", "--email", "-e", help="Email address"),
    company: str | None = typer.Option(None, "--company", "-c", help="Company name"),
    phone: str | None = typer.Option(None, "--phone", "-p", help="Phone number"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Create a new manager and a default portfolio."""
    asyncio.run(_create_manager(name, email, company, phone, use_json(json_output)))


async def _create_manager(
    name: str, email: str, company: str | None, phone: str | None, fmt_json: bool
) -> None:
    body: dict[str, Any] = {"name": name, "email": email}
    if company:
        body["company"] = company
    if phone:
        body["phone"] = phone

    if _http.is_sandbox():
        data = _http.post("/managers", body)
        if fmt_json:
            json_out(data)
        else:
            typer.echo(
                f"Created manager '{data['name']}' (id={data['manager_id']}, "
                f"portfolio={data['portfolio_id']})"
            )
        return

    container = get_container()
    from remi.application.core.models import Portfolio, PropertyManager
    from remi.types.text import slugify

    manager_id = slugify(f"manager:{name}")
    portfolio_id = slugify(f"portfolio:{name}")

    existing = await container.property_store.get_manager(manager_id)
    if existing:
        typer.echo(f"Manager '{name}' already exists (id={manager_id})", err=True)
        raise typer.Exit(1)

    await container.property_store.upsert_manager(
        PropertyManager(id=manager_id, name=name, email=email, company=company, phone=phone)
    )
    await container.property_store.upsert_portfolio(
        Portfolio(id=portfolio_id, manager_id=manager_id, name=f"{name} Portfolio")
    )

    if fmt_json:
        json_out({"manager_id": manager_id, "portfolio_id": portfolio_id, "name": name})
    else:
        typer.echo(f"Created manager '{name}' (id={manager_id}, portfolio={portfolio_id})")


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------


@cmd.command("review")
def review_manager(
    manager_id: str = typer.Argument(..., help="Manager ID"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Show a detailed review for a manager."""
    asyncio.run(_review_manager(manager_id, use_json(json_output)))


async def _review_manager(manager_id: str, fmt_json: bool) -> None:
    if _http.is_sandbox():
        data = _http.get(f"/managers/{manager_id}/review")
        if fmt_json:
            json_out(data)
        else:
            _render_review(data)
        return

    container = get_container()
    result = await container.manager_review.aggregate_manager(manager_id)
    if not result:
        typer.echo(f"Manager '{manager_id}' not found.", err=True)
        raise typer.Exit(1)
    data = result.model_dump()
    if fmt_json:
        json_out(data)
    else:
        _render_review(data)


def _render_review(data: dict[str, Any]) -> None:
    typer.echo(f"\nManager: {data.get('name', '?')}  ({data.get('email', '')})")
    if data.get("company"):
        typer.echo(f"Company: {data['company']}")
    typer.echo(
        f"Portfolios: {data.get('portfolio_count', 0)}  |  "
        f"Properties: {data.get('property_count', 0)}  |  "
        f"Units: {data.get('total_units', 0)}"
    )
    occ = data.get("occupancy_rate", 0)
    typer.echo(
        f"Occupied: {data.get('occupied', 0)} / {data.get('total_units', 0)}  "
        f"({float(str(occ)):.1f}%)"
    )
    typer.echo(
        f"Actual Rent: ${float(str(data.get('total_actual_rent', 0))):,.0f}  |  "
        f"Loss-to-Lease: ${float(str(data.get('total_loss_to_lease', 0))):,.0f}"
    )
    typer.echo(
        f"Delinquent Tenants: {data.get('delinquent_count', 0)}  |  "
        f"Balance: ${float(str(data.get('total_delinquent_balance', 0))):,.0f}"
    )
    typer.echo(
        f"Open Maintenance: {data.get('open_maintenance', 0)}  |  "
        f"Expiring Leases (90d): {data.get('expiring_leases_90d', 0)}"
    )


# ---------------------------------------------------------------------------
# assign
# ---------------------------------------------------------------------------


@cmd.command("assign")
def assign_properties(
    manager_id: str = typer.Argument(..., help="Manager ID to assign to"),
    property_ids: list[str] = typer.Argument(..., help="One or more property IDs"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Assign properties to a manager's portfolio."""
    asyncio.run(_assign_properties(manager_id, property_ids, use_json(json_output)))


async def _assign_properties(manager_id: str, property_ids: list[str], fmt_json: bool) -> None:
    if _http.is_sandbox():
        data = _http.post(f"/managers/{manager_id}/assign", {"property_ids": property_ids})
        if fmt_json:
            json_out(data)
        else:
            typer.echo(
                f"Assigned {data.get('assigned', 0)} properties to {manager_id}  "
                f"(already={data.get('already_assigned', 0)}, "
                f"not_found={data.get('not_found', [])})"
            )
        return

    container = get_container()
    ps = container.property_store

    mgr = await ps.get_manager(manager_id)
    if not mgr:
        typer.echo(f"Manager '{manager_id}' not found.", err=True)
        raise typer.Exit(1)

    portfolios = await ps.list_portfolios(manager_id=manager_id)
    if not portfolios:
        typer.echo(f"Manager '{manager_id}' has no portfolio.", err=True)
        raise typer.Exit(1)
    portfolio_id = portfolios[0].id

    assigned = already = 0
    not_found: list[str] = []
    for pid in property_ids:
        prop = await ps.get_property(pid)
        if not prop:
            not_found.append(pid)
            continue
        if prop.portfolio_id == portfolio_id:
            already += 1
            continue
        await ps.upsert_property(prop.model_copy(update={"portfolio_id": portfolio_id}))
        assigned += 1

    result = {
        "manager_id": manager_id,
        "assigned": assigned,
        "already_assigned": already,
        "not_found": not_found,
    }
    if fmt_json:
        json_out(result)
    else:
        typer.echo(
            f"Assigned {assigned} properties to {manager_id}  "
            f"(already={already}, not_found={not_found})"
        )


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------


@cmd.command("merge")
def merge_managers(
    source_id: str = typer.Argument(..., help="Source manager ID (will be deleted)"),
    target_id: str = typer.Argument(..., help="Target manager ID (receives properties)"),
    json_output: bool = typer.Option(False, "--json", "-j"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Move all properties from source manager to target, then delete source."""
    if not yes:
        typer.confirm(
            f"Move all properties from '{source_id}' to '{target_id}' and delete source?",
            abort=True,
        )
    asyncio.run(_merge_managers(source_id, target_id, use_json(json_output)))


async def _merge_managers(source_id: str, target_id: str, fmt_json: bool) -> None:
    if _http.is_sandbox():
        data = _http.post(
            "/managers/merge",
            {"source_manager_id": source_id, "target_manager_id": target_id},
        )
        if fmt_json:
            json_out(data)
        else:
            typer.echo(
                f"Moved {data.get('properties_moved', 0)} properties to '{target_id}'  "
                f"(source deleted={data.get('source_deleted', False)})"
            )
        return

    container = get_container()
    ps = container.property_store

    source = await ps.get_manager(source_id)
    target = await ps.get_manager(target_id)
    if not source:
        typer.echo(f"Source manager '{source_id}' not found.", err=True)
        raise typer.Exit(1)
    if not target:
        typer.echo(f"Target manager '{target_id}' not found.", err=True)
        raise typer.Exit(1)

    target_portfolios = await ps.list_portfolios(manager_id=target_id)
    if not target_portfolios:
        typer.echo(f"Target manager '{target_id}' has no portfolio.", err=True)
        raise typer.Exit(1)
    target_pf_id = target_portfolios[0].id

    moved = 0
    for spf in await ps.list_portfolios(manager_id=source_id):
        for prop in await ps.list_properties(portfolio_id=spf.id):
            await ps.upsert_property(prop.model_copy(update={"portfolio_id": target_pf_id}))
            moved += 1

    deleted = await ps.delete_manager(source_id)

    result = {
        "target_manager_id": target_id,
        "properties_moved": moved,
        "source_deleted": deleted,
    }
    if fmt_json:
        json_out(result)
    else:
        typer.echo(f"Moved {moved} properties to '{target_id}'  (source deleted={deleted})")
