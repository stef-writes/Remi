"""Intelligence CLI — dashboard, search, vacancies, trends, assertions."""

from __future__ import annotations

import asyncio

import typer

from remi.shell.cli.output import emit_error, emit_success

cli_group = typer.Typer(
    name="intelligence",
    help="Intelligence — dashboard, search, vacancies, trends.",
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
def dashboard(
    as_json: bool = typer.Option(True, "--json/--table", help="JSON or human table"),
) -> None:
    """Show portfolio dashboard overview."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get("/dashboard")
        emit_success(data, command="remi intelligence dashboard")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    result = _run(c.dashboard_resolver.get_overview())
    if as_json:
        emit_success(
            result.model_dump(mode="json"),
            command="remi intelligence dashboard",
        )
        return
    typer.echo(
        f"Portfolio: {result.total_properties} properties, "
        f"{result.total_units} units, "
        f"occupancy {result.occupancy_rate:.0%}"
    )


@cli_group.command()
def search(
    query: str = typer.Argument(help="Search query"),
    types: str | None = typer.Option(None, help="Entity type filter"),
    manager_id: str | None = typer.Option(None, help="Scope to manager"),
    limit: int = typer.Option(10, help="Max results"),
    as_json: bool = typer.Option(True, "--json/--table", help="JSON or human table"),
) -> None:
    """Search entities by name, address, or query."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get("/search", {
            "q": query,
            "types": types,
            "manager_id": manager_id,
            "limit": limit,
        })
        emit_success(
            data.get("results", data),
            command="remi intelligence search",
        )
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    results = _run(c.search_service.search(query))
    if as_json:
        emit_success(
            [r.model_dump(mode="json") for r in results],
            command="remi intelligence search",
        )
        return
    for r in results:
        typer.echo(f"  [{r.entity_type}] {r.name}  (score={r.score:.2f})")


@cli_group.command()
def vacancies(
    manager_id: str | None = typer.Option(None, help="Scope to manager"),
) -> None:
    """Vacancy tracker — vacant units with market rent at risk."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get("/dashboard/vacancies", {"manager_id": manager_id})
        emit_success(data, command="remi intelligence vacancies")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    result = _run(c.dashboard_resolver.vacancy_tracker(manager_id=manager_id))
    emit_success(
        result.model_dump(mode="json"),
        command="remi intelligence vacancies",
    )


@cli_group.command()
def trends(
    metric: str = typer.Argument(help="Metric: delinquency, occupancy"),
    manager_id: str | None = typer.Option(None, help="Scope to manager"),
    property_id: str | None = typer.Option(None, help="Scope to property"),
    periods: int = typer.Option(12, help="Number of periods"),
) -> None:
    """Time-series trends for a metric."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get(f"/dashboard/trends/{metric}", {
            "manager_id": manager_id,
            "property_id": property_id,
            "periods": periods,
        })
        emit_success(data, command="remi intelligence trends")
        return

    c = _container()
    _run(c.ensure_bootstrapped())

    if metric == "delinquency":
        result = _run(c.dashboard_resolver.delinquency_trend(
            manager_id=manager_id,
            property_id=property_id,
            periods=periods,
        ))
    elif metric == "occupancy":
        result = _run(c.dashboard_resolver.occupancy_trend(
            manager_id=manager_id,
            property_id=property_id,
            periods=periods,
        ))
    else:
        emit_error(
            "INVALID_METRIC",
            f"Unknown metric '{metric}'. Use: delinquency, occupancy",
            command="remi intelligence trends",
        )

    emit_success(
        result.model_dump(mode="json"),
        command="remi intelligence trends",
    )


@cli_group.command(name="assert-fact")
def assert_fact(
    entity_type: str = typer.Option(..., help="Entity type: PropertyManager, Property, Tenant"),
    properties: str = typer.Option(..., help="JSON object of properties to assert"),
    entity_id: str | None = typer.Option(None, help="Entity ID (auto-generated if omitted)"),
) -> None:
    """Record a fact or observation as a note with assertion provenance."""
    import json as _json

    if _is_remote():
        from remi.shell.cli.client import post

        data = post("/knowledge/assert", {
            "entity_type": entity_type,
            "properties": _json.loads(properties),
            "entity_id": entity_id,
        })
        emit_success(data, command="remi intelligence assert-fact")
        return

    c = _container()
    _run(c.ensure_bootstrapped())

    from remi.application.tools.assertions import _assert_fact

    result = _run(_assert_fact(
        c.property_store,
        c.event_store,
        c.event_bus,
        entity_type=entity_type,
        entity_id=entity_id,
        properties=_json.loads(properties),
    ))
    emit_success(result, command="remi intelligence assert-fact")


@cli_group.command(name="add-context")
def add_context(
    entity_type: str = typer.Option(..., help="Entity type"),
    entity_id: str = typer.Option(..., help="Entity ID"),
    context: str = typer.Option(..., help="Context text to attach"),
) -> None:
    """Attach user context to an entity."""
    if _is_remote():
        from remi.shell.cli.client import post

        data = post("/knowledge/context", {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "context": context,
        })
        emit_success(data, command="remi intelligence add-context")
        return

    c = _container()
    _run(c.ensure_bootstrapped())

    from remi.application.tools.assertions import _add_context

    result = _run(_add_context(
        c.property_store,
        entity_type=entity_type,
        entity_id=entity_id,
        context=context,
    ))
    emit_success(result, command="remi intelligence add-context")
