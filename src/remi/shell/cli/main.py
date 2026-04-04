"""CLI mountpoint — registers all slice CLIs. No commands defined here."""

from __future__ import annotations

import typer

from remi.application.cli.agents import ai_cmd
from remi.application.cli.bench import cmd as bench_cmd
from remi.application.cli.db import cmd as db_cmd
from remi.application.cli.demo import cmd as demo_cmd
from remi.application.cli.documents import cmd as documents_cmd
from remi.application.cli.graph import cmd as graph_cmd
from remi.application.cli.ontology import cmd as onto_cmd
from remi.application.cli.properties import (
    leases_cmd,
    maintenance_cmd,
    portfolio_cmd,
    property_cmd,
    report_cmd,
    tenants_cmd,
    units_cmd,
)
from remi.application.cli.research import cmd as research_cmd
from remi.application.cli.search import cmd as search_cmd
from remi.application.cli.seed import cmd as seed_cmd
from remi.application.cli.trace import cmd as trace_cmd
from remi.application.cli.vectors import cmd as vectors_cmd

cli = typer.Typer(
    name="remi",
    help="REMI — Real Estate Management Intelligence.",
    no_args_is_help=True,
)

cli.add_typer(ai_cmd)
cli.add_typer(research_cmd)
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
cli.add_typer(seed_cmd)
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
        from remi.application.cli.dashboard import run as run_dashboard
    except ImportError as exc:
        typer.echo(f"Dashboard requires textual: {exc}", err=True)
        raise typer.Exit(1) from exc
    run_dashboard(agent=agent, verbose=verbose)


@cli.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
    seed: str = typer.Option(
        "",
        "--seed",
        help="Seed from this report directory at startup.",
    ),
    force_seed: bool = typer.Option(
        False,
        "--force-seed",
        help="Re-run LLM pipeline even if a seed cache exists.",
    ),
) -> None:
    """Start the API server."""
    import os

    import uvicorn

    from remi.application.cli.banner import print_banner

    if seed:
        os.environ["REMI_SEED_DIR"] = seed
    if force_seed:
        os.environ["REMI_FORCE_SEED"] = "1"

    print_banner(host=host, port=port, reload=reload, seed=bool(seed))

    uvicorn.run(
        "remi.shell.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


app = cli
