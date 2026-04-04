"""``remi seed`` — populate the property store from AppFolio report exports."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

cmd = typer.Typer(name="seed", help="Seed REMI from AppFolio report exports.")


async def _seed(report_dir: Path | None = None) -> None:
    from remi.application.cli.shared import get_container_async

    container = await get_container_async()
    result = await container.seed_service.seed_from_reports(report_dir)

    if result.errors:
        for err in result.errors:
            typer.echo(f"  WARNING: {err}", err=True)

    typer.echo(
        f"Seeded: {result.managers_created} managers, "
        f"{result.properties_created} properties, "
        f"{len(result.reports_ingested)} reports ingested, "
        f"{result.auto_assigned} auto-assigned, "
        f"{result.signals_produced} signals."
    )


@cmd.callback(invoke_without_command=True)
def seed(
    report_dir: str = typer.Option(
        "",
        "--dir",
        "-d",
        help="Path to report directory (defaults to data/sample_reports/Alex_Budavich_Reports/)",
    ),
) -> None:
    """Ingest AppFolio XLSX exports (property dir, delinquency, lease, rent roll)."""
    path = Path(report_dir) if report_dir else None
    asyncio.run(_seed(path))
