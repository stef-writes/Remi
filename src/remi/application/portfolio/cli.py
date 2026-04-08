"""Portfolio CLI — managers, properties, rent-roll, manager-review, rankings."""

from __future__ import annotations

import asyncio

import typer

from remi.shell.cli.output import emit_error, emit_success

cli_group = typer.Typer(
    name="portfolio",
    help="Portfolio queries — managers, properties, units, rent-roll, rankings.",
)


def _run(coro):  # noqa: ANN001, ANN202
    return asyncio.get_event_loop().run_until_complete(coro)


def _is_remote() -> bool:
    from remi.shell.cli.client import get_api_url

    return get_api_url() is not None


def _container():  # noqa: ANN202
    from remi.shell.config.container import Container

    return Container()


@cli_group.command()
def managers(
    as_json: bool = typer.Option(True, "--json/--table", help="JSON (default) or human table"),
) -> None:
    """List managers with portfolio metrics."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get("/managers")
        if as_json:
            emit_success(data.get("managers", data), command="remi portfolio managers")
            return
        for m in data.get("managers", []):
            typer.echo(f"  {m['name']:<30}")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    result = _run(c.manager_resolver.list_managers())
    if as_json:
        emit_success(
            [m.model_dump(mode="json") for m in result],
            command="remi portfolio managers",
        )
        return
    for m in result:
        typer.echo(f"  {m.name:<30} {m.property_count} props  occ={m.metrics.occupancy_rate:.0%}")


@cli_group.command()
def properties(
    manager_id: str | None = typer.Option(None, help="Filter by manager ID"),
    as_json: bool = typer.Option(True, "--json/--table", help="JSON or human table"),
) -> None:
    """List properties."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get("/properties", {"manager_id": manager_id})
        emit_success(data.get("properties", data), command="remi portfolio properties")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    result = _run(c.property_resolver.list_properties(manager_id=manager_id))
    if as_json:
        emit_success(
            [p.model_dump(mode="json") for p in result.items],
            command="remi portfolio properties",
        )
        return
    for p in result.items:
        typer.echo(f"  {p.name:<40} {p.unit_count} units")


@cli_group.command(name="rent-roll")
def rent_roll(
    property_id: str = typer.Argument(help="Property ID"),
    as_json: bool = typer.Option(True, "--json/--table", help="JSON or human table"),
) -> None:
    """Show rent roll for a property."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get(f"/properties/{property_id}/rent-roll")
        emit_success(data, command="remi portfolio rent-roll")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    result = _run(c.rent_roll_resolver.get_rent_roll(property_id))
    if as_json:
        emit_success(result.model_dump(mode="json"), command="remi portfolio rent-roll")
        return
    typer.echo(f"Rent roll: {result.property_name} ({len(result.rows)} units)")
    for row in result.rows:
        typer.echo(f"  {row.unit_number:<10} ${row.monthly_rent:>8,.0f}  {row.occupancy_status}")


@cli_group.command(name="manager-review")
def manager_review(
    manager_id: str = typer.Argument(help="Manager ID to review"),
) -> None:
    """Complete manager review — summary, delinquency, vacancies, expirations."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get(f"/managers/{manager_id}/review")
        emit_success(data, command="remi portfolio manager-review")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    summary = _run(c.manager_resolver.aggregate_manager(manager_id))
    if not summary:
        emit_error(
            "MANAGER_NOT_FOUND",
            f"No manager found with ID '{manager_id}'",
            command="remi portfolio manager-review",
        )

    result = {"summary": summary.model_dump(mode="json")}

    if summary.total_delinquent_balance > 0:
        board = _run(c.dashboard_resolver.delinquency_board(manager_id=manager_id))
        result["delinquency"] = board.model_dump(mode="json")

    if summary.metrics.expiring_leases_90d > 0:
        cal = _run(c.dashboard_resolver.lease_expiration_calendar(
            days=90, manager_id=manager_id,
        ))
        result["lease_expirations"] = cal.model_dump(mode="json")

    if summary.metrics.vacant > 0:
        vac = _run(c.dashboard_resolver.vacancy_tracker(manager_id=manager_id))
        result["vacancies"] = vac.model_dump(mode="json")

    action_items = _run(c.property_store.list_action_items(manager_id=manager_id))
    if action_items:
        result["action_items"] = [ai.model_dump(mode="json") for ai in action_items]

    notes = _run(c.property_store.list_notes(
        entity_type="PropertyManager", entity_id=manager_id,
    ))
    if notes:
        result["notes"] = [n.model_dump(mode="json") for n in notes]

    emit_success(result, command="remi portfolio manager-review")


@cli_group.command()
def rankings(
    sort_by: str = typer.Option("delinquency_rate", help="Metric to sort by"),
    ascending: bool = typer.Option(False, help="Ascending order"),
    limit: int = typer.Option(10, help="Max managers to return"),
) -> None:
    """Rank managers by any metric."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get("/managers/rankings", {
            "sort_by": sort_by,
            "ascending": str(ascending).lower(),
            "limit": limit,
        })
        emit_success(data.get("rankings", data), command="remi portfolio rankings")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    result = _run(c.manager_resolver.rank_managers(
        sort_by=sort_by,
        ascending=ascending,
        limit=limit,
    ))
    emit_success(result.model_dump(mode="json"), command="remi portfolio rankings")
