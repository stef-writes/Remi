"""``remi demo`` — one-command demo: check prereqs, seed, start server."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from remi.application.services.seeding.service import discover_reports

console = Console(stderr=True)

cmd = typer.Typer(name="demo", help="Launch a full demo — seed + serve in one command.")


def _check_key(name: str, env_var: str) -> bool:
    val = os.environ.get(env_var, "")
    if val:
        console.print(f"  [green]OK[/green]  {name}")
        return True
    console.print(f"  [red]MISSING[/red]  {name} ({env_var})")
    return False


def _preflight(report_dir: Path) -> bool:
    """Verify prerequisites before launching the demo."""
    ok = True

    header = Text()
    header.append("REMI Demo", style="bold cyan")
    header.append("  Pre-flight checks", style="dim")
    console.print(Panel(header, border_style="cyan", padding=(0, 2)))
    console.print()

    # API keys
    console.print("[bold]API Keys[/bold]")
    has_llm = (
        _check_key("Anthropic", "ANTHROPIC_API_KEY")
        or _check_key("OpenAI", "OPENAI_API_KEY")
        or _check_key("Google", "GOOGLE_API_KEY")
    )
    if not has_llm:
        console.print("  [red]At least one LLM key is required for ingestion.[/red]")
        ok = False

    _check_key("OpenAI (embeddings)", "OPENAI_API_KEY")
    console.print()

    # Report directory
    console.print("[bold]Report Data[/bold]")
    if not report_dir.exists():
        console.print(f"  [red]Directory not found:[/red] {report_dir}")
        ok = False
    else:
        reports = discover_reports(report_dir)
        if not reports:
            console.print(f"  [red]No report files found in[/red] {report_dir}")
            ok = False
        else:
            console.print(f"  [green]OK[/green]  {len(reports)} report file(s) in {report_dir}")
            for r in reports:
                console.print(f"       {r.name}")
    console.print()

    return ok


async def _seed_and_report(report_dir: Path) -> bool:
    from remi.application.cli.shared import get_container_async

    container = await get_container_async()
    console.print("[bold]Seeding...[/bold]")
    result = await container.seed_service.seed_from_reports(report_dir)

    if result.errors:
        for err in result.errors:
            console.print(f"  [yellow]WARNING[/yellow] {err}")

    console.print(
        f"  [green]OK[/green]  {result.managers_created} managers, "
        f"{result.properties_created} properties, "
        f"{len(result.reports_ingested)} reports, "
        f"{result.signals_produced} signals, "
        f"{result.history_snapshots} history snapshots"
    )
    console.print()
    return result.ok or len(result.reports_ingested) > 0


def _start_server(host: str, port: int) -> None:
    import uvicorn

    from remi.application.cli.banner import print_banner

    print_banner(host=host, port=port, reload=False, seed=False)
    uvicorn.run("remi.shell.api.main:app", host=host, port=port)


async def _generate_and_report() -> bool:
    from remi.application.services.seeding.synthetic import generate_synthetic_portfolio
    from remi.application.cli.shared import get_container_async

    container = await get_container_async()
    console.print("[bold]Generating synthetic portfolio...[/bold]")
    result = await generate_synthetic_portfolio(container.property_store)

    console.print(
        f"  [green]OK[/green]  {result.managers} managers, "
        f"{result.properties} properties, "
        f"{result.units} units, "
        f"{result.tenants} tenants, "
        f"{result.leases} leases"
    )

    console.print("  Running signal pipeline...")
    sig_result = await container.signal_pipeline.run_all()
    console.print(f"  [green]OK[/green]  {sig_result.produced} signals")

    console.print("  Running embedding pipeline...")
    embed_result = await container.embedding_pipeline.run_full()
    console.print(f"  [green]OK[/green]  {embed_result.embedded} entities embedded")
    console.print()
    return True


@cmd.callback(invoke_without_command=True)
def demo(
    report_dir: str = typer.Option(
        "",
        "--dir",
        "-d",
        help="Directory containing AppFolio XLSX/CSV exports.",
    ),
    generate: bool = typer.Option(
        False,
        "--generate",
        "-g",
        help="Use synthetic demo data (no files or API keys needed for seeding).",
    ),
    host: str = typer.Option("127.0.0.1", help="API host"),
    port: int = typer.Option(8000, help="API port"),
    skip_checks: bool = typer.Option(False, "--skip-checks", help="Skip pre-flight checks"),
) -> None:
    """One-command demo: check prerequisites, seed data, start the server."""
    from remi.agent.observe.logging import configure_logging
    from remi.shell.config.settings import load_settings

    load_settings()
    configure_logging(level="INFO", format="console")

    if generate:
        seeded = asyncio.run(_generate_and_report())
    elif report_dir:
        path = Path(report_dir)
        if not skip_checks:
            if not _preflight(path):
                console.print(
                    "[red]Pre-flight checks failed. "
                    "Fix the issues above or pass --skip-checks.[/red]"
                )
                raise typer.Exit(1)
        seeded = asyncio.run(_seed_and_report(path))
    else:
        console.print(
            "Pass --dir <path> or --generate. See --help.",
            style="red",
        )
        raise typer.Exit(1)

    if not seeded:
        console.print("[red]Seeding failed — no data loaded.[/red]")
        raise typer.Exit(1)

    console.print("[bold]Starting API server...[/bold]")
    console.print(f"  Open [cyan]http://localhost:3000[/cyan] (frontend)")
    console.print(f"  API at [cyan]http://{host}:{port}[/cyan]")
    console.print()

    _start_server(host, port)
