"""Operations CLI — leases, maintenance, delinquency, actions, notes."""

from __future__ import annotations

import asyncio
import uuid

import typer

from remi.shell.cli.output import emit_error, emit_success

cli_group = typer.Typer(
    name="operations",
    help="Operations — leases, maintenance, delinquency, actions, notes.",
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
def leases(
    property_id: str | None = typer.Option(None, help="Filter by property ID"),
    manager_id: str | None = typer.Option(None, help="Filter by manager ID"),
    status: str | None = typer.Option(None, help="Filter by status"),
    as_json: bool = typer.Option(True, "--json/--table", help="JSON or human table"),
) -> None:
    """List leases."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get("/leases", {
            "property_id": property_id,
            "manager_id": manager_id,
            "status": status,
        })
        emit_success(data, command="remi operations leases")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    result = _run(c.lease_resolver.list_leases(
        property_id=property_id, status=status,
    ))
    if as_json:
        emit_success(result.model_dump(mode="json"), command="remi operations leases")
        return
    typer.echo(f"Leases: {result.total}")
    for le in result.items:
        typer.echo(f"  {le.tenant:<30} ${le.rent:>8,.0f}  {le.status}")


@cli_group.command()
def maintenance(
    property_id: str | None = typer.Option(None, help="Filter by property ID"),
    manager_id: str | None = typer.Option(None, help="Filter by manager ID"),
    as_json: bool = typer.Option(True, "--json/--table", help="JSON or human table"),
) -> None:
    """List maintenance requests."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get("/maintenance", {
            "property_id": property_id,
            "manager_id": manager_id,
        })
        emit_success(data, command="remi operations maintenance")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    result = _run(c.maintenance_resolver.list_requests(property_id=property_id))
    if as_json:
        emit_success(
            result.model_dump(mode="json"),
            command="remi operations maintenance",
        )
        return
    typer.echo(f"Maintenance requests: {result.total}")
    for req in result.items:
        typer.echo(f"  {req.title:<40} {req.status}  {req.priority}")


@cli_group.command()
def delinquency(
    manager_id: str | None = typer.Option(None, help="Scope to manager"),
) -> None:
    """Delinquency board — delinquent tenants with balances."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get("/dashboard/delinquency", {"manager_id": manager_id})
        emit_success(data, command="remi operations delinquency")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    board = _run(c.dashboard_resolver.delinquency_board(manager_id=manager_id))
    emit_success(board.model_dump(mode="json"), command="remi operations delinquency")


@cli_group.command(name="expiring-leases")
def expiring_leases(
    days: int = typer.Option(90, help="Look-ahead window in days"),
    manager_id: str | None = typer.Option(None, help="Scope to manager"),
) -> None:
    """Leases expiring within N days."""
    if _is_remote():
        from remi.shell.cli.client import get

        data = get("/dashboard/expiring-leases", {
            "days": days, "manager_id": manager_id,
        })
        emit_success(data, command="remi operations expiring-leases")
        return

    c = _container()
    _run(c.ensure_bootstrapped())
    calendar = _run(c.dashboard_resolver.lease_expiration_calendar(
        days=days, manager_id=manager_id,
    ))
    emit_success(
        calendar.model_dump(mode="json"),
        command="remi operations expiring-leases",
    )


@cli_group.command(name="create-action")
def create_action(
    title: str = typer.Option(..., help="Action item title"),
    manager_id: str = typer.Option(..., help="Manager ID"),
    priority: str = typer.Option("medium", help="low, medium, high, critical"),
    description: str = typer.Option("", help="Description"),
    tenant_id: str | None = typer.Option(None, help="Related tenant ID"),
    property_id: str | None = typer.Option(None, help="Related property ID"),
) -> None:
    """Create an action item."""
    if _is_remote():
        from remi.shell.cli.client import post

        data = post("/actions", {
            "title": title,
            "manager_id": manager_id,
            "priority": priority,
            "description": description or None,
            "tenant_id": tenant_id,
            "property_id": property_id,
        })
        emit_success(data, command="remi operations create-action")
        return

    from remi.application.core.models import ActionItem, Priority

    try:
        p = Priority(priority.lower())
    except ValueError:
        emit_error(
            "INVALID_PRIORITY",
            f"Invalid priority '{priority}'. Use: low, medium, high, critical",
            command="remi operations create-action",
        )

    item = ActionItem(
        id=f"ai-{uuid.uuid4().hex[:8]}",
        title=title,
        description=description or None,
        manager_id=manager_id,
        priority=p,
        tenant_id=tenant_id,
        property_id=property_id,
    )
    c = _container()
    _run(c.ensure_bootstrapped())
    result = _run(c.property_store.upsert_action_item(item))
    emit_success(
        {
            "id": result.entity.id,
            "title": result.entity.title,
            "outcome": result.outcome.value,
        },
        command="remi operations create-action",
    )


@cli_group.command(name="create-note")
def create_note(
    content: str = typer.Option(..., help="Note content"),
    entity_type: str = typer.Option(
        ..., help="Entity type: PropertyManager, Property, Tenant, etc.",
    ),
    entity_id: str = typer.Option(..., help="Entity ID"),
) -> None:
    """Create a note attached to an entity."""
    if _is_remote():
        from remi.shell.cli.client import post

        data = post("/notes", {
            "content": content,
            "entity_type": entity_type,
            "entity_id": entity_id,
        })
        emit_success(data, command="remi operations create-note")
        return

    from remi.application.core.models import Note

    note = Note(
        id=f"note-{uuid.uuid4().hex[:8]}",
        content=content,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    c = _container()
    _run(c.ensure_bootstrapped())
    result = _run(c.property_store.upsert_note(note))
    emit_success(
        {"id": result.entity.id, "outcome": result.outcome.value},
        command="remi operations create-note",
    )
