"""CLI entry point for REMI — Real Estate Management Intelligence."""

from __future__ import annotations

import typer

from remi.cli.agents import ask_cmd, chat_cmd
from remi.cli.documents import cmd as documents_cmd
from remi.cli.ontology import cmd as onto_cmd
from remi.cli.properties import (
    leases_cmd,
    maintenance_cmd,
    portfolio_cmd,
    property_cmd,
    report_cmd,
    tenants_cmd,
    units_cmd,
)
from remi.cli.seed import cmd as seed_cmd

cli = typer.Typer(
    name="remi",
    help="REMI — Real Estate Management Intelligence.",
    no_args_is_help=True,
)

# Agent commands
cli.add_typer(ask_cmd)
cli.add_typer(chat_cmd)

# Property management commands
cli.add_typer(portfolio_cmd)
cli.add_typer(property_cmd)
cli.add_typer(units_cmd)
cli.add_typer(leases_cmd)
cli.add_typer(maintenance_cmd)
cli.add_typer(tenants_cmd)
cli.add_typer(report_cmd)
cli.add_typer(documents_cmd)
cli.add_typer(onto_cmd)
cli.add_typer(seed_cmd)


@cli.command()
def dashboard(
    agent: str = typer.Option("director", "--agent", "-a", help="Agent to chat with"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show LLM token deltas"),
) -> None:
    """Open the live knowledge physics dashboard (Textual TUI)."""
    try:
        from remi.cli.dashboard import run as run_dashboard
    except ImportError as exc:
        typer.echo(f"Dashboard requires textual: {exc}", err=True)
        raise typer.Exit(1) from exc
    run_dashboard(agent=agent, verbose=verbose)


@cli.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
    seed_demo: bool = typer.Option(False, "--seed", help="Load demo data at startup"),
) -> None:
    """Start the API server."""
    import os

    import uvicorn

    from remi.cli.banner import print_banner

    if seed_demo:
        os.environ["REMI_SEED_DEMO"] = "1"

    print_banner(host=host, port=port, reload=reload, seed_demo=seed_demo)

    uvicorn.run(
        "remi.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


app = cli
