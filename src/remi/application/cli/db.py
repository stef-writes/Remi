"""``remi db`` — database lifecycle commands for development and demos."""

from __future__ import annotations

import asyncio

import typer

cmd = typer.Typer(name="db", help="Database lifecycle — init, reset, status.")


async def _init() -> None:
    from remi.application.cli.shared import get_container_async

    container = await get_container_async()
    backend = container.settings.state_store.backend

    if backend != "postgres":
        typer.echo(f"Backend is '{backend}' — tables created in-memory at startup.")
        return

    typer.echo("Tables created (or verified) against Postgres.")


async def _reset(seed_dir: str | None) -> None:
    from pathlib import Path

    import structlog

    from remi.application.cli.shared import get_container

    log = structlog.get_logger("remi.db.reset")
    container = get_container()
    engine = container._db_engine

    if engine is not None:
        from sqlmodel import SQLModel

        typer.echo("Dropping all tables...")
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        typer.echo("Recreating tables...")
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        typer.echo("Postgres reset complete.")
    else:
        typer.echo("Backend is in-memory — nothing to drop.")

    from remi.application.infra.ontology.seed import seed_knowledge_graph

    await seed_knowledge_graph(container.knowledge_graph)
    typer.echo("Knowledge graph re-seeded.")

    if seed_dir:
        typer.echo(f"Seeding from {seed_dir}...")
        result = await container.seed_service.seed_from_reports(Path(seed_dir))
        if result.errors:
            for err in result.errors:
                typer.echo(f"  WARNING: {err}", err=True)
        typer.echo(
            f"Seeded: {result.managers_created} managers, "
            f"{result.properties_created} properties, "
            f"{len(result.reports_ingested)} reports, "
            f"{result.signals_produced} signals."
        )
    else:
        typer.echo("Skipping seed (pass --seed <dir> to seed after reset).")


async def _status() -> None:
    from remi.application.cli.shared import get_container

    container = get_container()
    settings = container.settings
    backend = settings.state_store.backend

    typer.echo(f"Backend:    {backend}")
    if backend == "postgres":
        dsn = settings.state_store.dsn or settings.secrets.database_url
        masked = dsn[:dsn.index("@") + 1] + "***" if "@" in dsn else dsn[:20] + "..."
        typer.echo(f"DSN:        {masked}")

    await container.ensure_bootstrapped()

    managers = await container.property_store.list_managers()
    properties = await container.property_store.list_properties()
    docs = await container.document_store.list_documents()

    typer.echo(f"Managers:   {len(managers)}")
    typer.echo(f"Properties: {len(properties)}")
    typer.echo(f"Documents:  {len(docs)}")

    seeded = len(managers) > 0 or len(properties) > 0
    typer.echo(f"Seeded:     {'yes' if seeded else 'no'}")


@cmd.command()
def init() -> None:
    """Ensure database tables exist (Postgres) or confirm in-memory mode."""
    asyncio.run(_init())


@cmd.command()
def reset(
    seed_dir: str = typer.Option(
        "",
        "--seed",
        help="After reset, seed from this report directory.",
    ),
) -> None:
    """Drop all tables, recreate, and optionally re-seed."""
    asyncio.run(_reset(seed_dir or None))


@cmd.command()
def status() -> None:
    """Show backend type, connection info, and entity counts."""
    asyncio.run(_status())
