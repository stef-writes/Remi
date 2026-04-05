"""``remi demo`` — one-command demo: check prereqs, load reports, start server."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from remi.application.services.seeding import discover_reports

console = Console(stderr=True)

cmd = typer.Typer(name="demo", help="Launch a full demo — load reports + serve in one command.")


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


async def _load_and_report(report_dir: Path) -> bool:
    from remi.application.cli.shared import get_container_async

    container = await get_container_async()
    console.print("[bold]Loading reports...[/bold]")
    result = await container.portfolio_loader.load_reports(report_dir)

    if result.errors:
        for err in result.errors:
            console.print(f"  [yellow]WARNING[/yellow] {err}")

    console.print(
        f"  [green]OK[/green]  {result.files_processed} files, "
        f"{result.total_entities} entities, "
        f"{result.total_relationships} relationships, "
        f"{result.total_embedded} embedded"
    )
    console.print()
    return result.files_processed > 0


def _start_server(host: str, port: int) -> None:
    import uvicorn

    from remi.application.cli.banner import print_banner

    print_banner(host=host, port=port, reload=False, loading=False)
    uvicorn.run("remi.shell.api.main:app", host=host, port=port)


@cmd.callback(invoke_without_command=True)
def demo(
    report_dir: str = typer.Option(
        "",
        "--dir",
        "-d",
        help="Directory containing AppFolio XLSX/CSV exports.",
    ),
    host: str = typer.Option("127.0.0.1", help="API host"),
    port: int = typer.Option(8000, help="API port"),
    skip_checks: bool = typer.Option(False, "--skip-checks", help="Skip pre-flight checks"),
) -> None:
    """One-command demo: check prerequisites, load reports, start the server."""
    from remi.agent.observe import configure_logging
    from remi.shell.config.settings import load_settings

    load_settings()
    configure_logging(level="INFO", format="console")

    if not report_dir:
        console.print(
            "Pass --dir <path>. See --help.",
            style="red",
        )
        raise typer.Exit(1)

    path = Path(report_dir)
    if not skip_checks and not _preflight(path):
        console.print(
            "[red]Pre-flight checks failed. "
            "Fix the issues above or pass --skip-checks.[/red]"
        )
        raise typer.Exit(1)
    loaded = asyncio.run(_load_and_report(path))

    if not loaded:
        console.print("[red]Report loading failed — no data loaded.[/red]")
        raise typer.Exit(1)

    console.print("[bold]Starting API server...[/bold]")
    console.print("  Open [cyan]http://localhost:3000[/cyan] (frontend)")
    console.print(f"  API at [cyan]http://{host}:{port}[/cyan]")
    console.print()

    _start_server(host, port)
