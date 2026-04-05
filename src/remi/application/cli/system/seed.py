"""``remi load`` — load AppFolio report exports into the property store."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

cmd = typer.Typer(name="load", help="Load AppFolio report exports into REMI.")


async def _run(report_dir: Path | None = None, manager: str | None = None) -> None:
    from remi.application.cli.shared import get_container_async

    container = await get_container_async()

    if report_dir is None:
        typer.echo("No report directory specified. Use --dir <path>.", err=True)
        raise typer.Exit(1)

    result = await container.portfolio_loader.load_reports(
        report_dir,
        manager=manager,
    )

    if result.errors:
        for err in result.errors:
            typer.echo(f"  WARNING: {err}", err=True)

    typer.echo(
        f"Loaded: {result.files_processed} files, "
        f"{result.total_entities} entities, "
        f"{result.total_relationships} relationships, "
        f"{result.total_embedded} embedded."
    )


@cmd.callback(invoke_without_command=True)
def load(
    report_dir: str = typer.Option(
        "",
        "--dir",
        "-d",
        help="Path to directory containing AppFolio report exports",
    ),
    manager: str = typer.Option(
        "",
        "--manager",
        "-m",
        help="Manager tag to associate with all ingested data",
    ),
) -> None:
    """Load AppFolio exports (property directory, rent roll, delinquency, lease expiration).

    Property Directory files are detected automatically and processed first,
    ensuring manager and portfolio associations are established before other
    reports are ingested.
    """
    path = Path(report_dir) if report_dir else None
    asyncio.run(_run(path, manager=manager or None))
