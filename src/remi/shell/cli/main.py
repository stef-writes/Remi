"""CLI mountpoint — registers all slice CLIs. No commands defined here."""

from __future__ import annotations

import typer

from remi.application.cli.intelligence.graph import cmd as graph_cmd
from remi.application.cli.intelligence.ontology import cmd as onto_cmd
from remi.application.cli.intelligence.research import cmd as research_cmd
from remi.application.cli.intelligence.search import cmd as search_cmd
from remi.application.cli.intelligence.trace import cmd as trace_cmd
from remi.application.cli.operations.leases import cmd as leases_cmd
from remi.application.cli.operations.maintenance import cmd as maintenance_cmd
from remi.application.cli.operations.tenants import cmd as tenants_cmd
from remi.application.cli.portfolio.managers import cmd as managers_cmd
from remi.application.cli.portfolio.portfolios import cmd as portfolio_cmd
from remi.application.cli.portfolio.property import cmd as property_cmd
from remi.application.cli.portfolio.rent_roll import cmd as report_cmd
from remi.application.cli.portfolio.units import cmd as units_cmd
from remi.application.cli.system.agents import ai_cmd
from remi.application.cli.system.bench import cmd as bench_cmd
from remi.application.cli.system.db import cmd as db_cmd
from remi.application.cli.system.demo import cmd as demo_cmd
from remi.application.cli.system.documents import cmd as documents_cmd
from remi.application.cli.system.seed import cmd as load_cmd
from remi.application.cli.system.vectors import cmd as vectors_cmd

cli = typer.Typer(
    name="remi",
    help="REMI — Real Estate Management Intelligence.",
    no_args_is_help=True,
)

cli.add_typer(ai_cmd)
cli.add_typer(research_cmd)
cli.add_typer(managers_cmd)
cli.add_typer(portfolio_cmd)
cli.add_typer(property_cmd)
cli.add_typer(units_cmd)
cli.add_typer(leases_cmd)
cli.add_typer(maintenance_cmd)
cli.add_typer(tenants_cmd)
cli.add_typer(report_cmd)
cli.add_typer(documents_cmd)
cli.add_typer(onto_cmd)
cli.add_typer(search_cmd)
cli.add_typer(load_cmd)
cli.add_typer(db_cmd)
cli.add_typer(demo_cmd)
cli.add_typer(graph_cmd)
cli.add_typer(trace_cmd)
cli.add_typer(vectors_cmd)
cli.add_typer(bench_cmd)


@cli.command()
def dashboard(
    agent: str = typer.Option("director", "--agent", "-a", help="Agent to chat with"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show LLM token deltas"),
) -> None:
    """Open the live portfolio dashboard (Textual TUI)."""
    try:
        from remi.application.cli.intelligence.dashboard import run as run_dashboard
    except ImportError as exc:
        typer.echo(f"Dashboard requires textual: {exc}", err=True)
        raise typer.Exit(1) from exc
    run_dashboard(agent=agent, verbose=verbose)


@cli.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
    load: str = typer.Option(
        "",
        "--load",
        help="Load reports from this directory at startup.",
    ),
) -> None:
    """Start the API server."""
    import os

    import uvicorn

    from remi.application.cli.banner import print_banner

    if load:
        os.environ["REMI_LOAD_DIR"] = load

    print_banner(host=host, port=port, reload=reload, loading=bool(load))

    uvicorn.run(
        "remi.shell.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


app = cli
