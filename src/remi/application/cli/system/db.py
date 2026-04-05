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


async def _reset(report_dir: str | None) -> None:
    from pathlib import Path

    from remi.application.cli.shared import get_container

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
    typer.echo("Knowledge graph bootstrapped.")

    if report_dir:
        typer.echo(f"Loading reports from {report_dir}...")
        result = await container.portfolio_loader.load_reports(Path(report_dir))
        if result.errors:
            for err in result.errors:
                typer.echo(f"  WARNING: {err}", err=True)
        typer.echo(
            f"Loaded: {result.files_processed} files, "
            f"{result.total_entities} entities, "
            f"{result.total_relationships} relationships."
        )
    else:
        typer.echo("Skipping report load (pass --load <dir> to load after reset).")


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
    docs = await container.content_store.list_documents()

    typer.echo(f"Managers:   {len(managers)}")
    typer.echo(f"Properties: {len(properties)}")
    typer.echo(f"Documents:  {len(docs)}")

    has_data = len(managers) > 0 or len(properties) > 0
    typer.echo(f"Data:       {'loaded' if has_data else 'empty'}")


@cmd.command()
def init() -> None:
    """Ensure database tables exist (Postgres) or confirm in-memory mode."""
    asyncio.run(_init())


@cmd.command()
def reset(
    report_dir: str = typer.Option(
        "",
        "--load",
        help="After reset, load reports from this directory.",
    ),
) -> None:
    """Drop all tables, recreate, and optionally load reports."""
    asyncio.run(_reset(report_dir or None))


@cmd.command()
def status() -> None:
    """Show backend type, connection info, and entity counts."""
    asyncio.run(_status())
