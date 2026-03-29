"""CLI entry point for REMI — Real Estate Management Intelligence.

Each subcommand lives in its own module under remi.interfaces.cli,
grouped by domain: properties/, agents/, framework/.
The CLI is the primary interface for both humans and agents — every
capability is discoverable via --help and returns structured JSON
when piped or when --json is passed.
"""

from __future__ import annotations

import typer

from remi.interfaces.cli.agents import ask_cmd, chat_cmd
from remi.interfaces.cli.documents import cmd as documents_cmd
from remi.interfaces.cli.framework import app_cmd, node_cmd, provider_cmd, tool_cmd
from remi.interfaces.cli.knowledge import cmd as kb_cmd
from remi.interfaces.cli.ontology import cmd as onto_cmd
from remi.interfaces.cli.trace import cmd as trace_cmd
from remi.interfaces.cli.vectors import cmd as vectors_cmd
from remi.interfaces.cli.properties import (
    leases_cmd,
    maintenance_cmd,
    portfolio_cmd,
    property_cmd,
    report_cmd,
    tenants_cmd,
    units_cmd,
)

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
cli.add_typer(kb_cmd)
cli.add_typer(onto_cmd)
cli.add_typer(trace_cmd)
cli.add_typer(vectors_cmd)

# Framework commands
cli.add_typer(app_cmd)
cli.add_typer(node_cmd)
cli.add_typer(tool_cmd)
cli.add_typer(provider_cmd)


@cli.command()
def dashboard(
    agent: str = typer.Option("director", "--agent", "-a", help="Agent to chat with"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show LLM token deltas"),
) -> None:
    """Open the live knowledge physics dashboard (Textual TUI)."""
    try:
        from remi.interfaces.cli.dashboard import run as run_dashboard
    except ImportError as exc:
        typer.echo(f"Dashboard requires textual: {exc}", err=True)
        raise typer.Exit(1) from exc
    run_dashboard(agent=agent, verbose=verbose)


@cli.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
) -> None:
    """Start the API server."""
    import uvicorn

    uvicorn.run(
        "remi.interfaces.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


app = cli
