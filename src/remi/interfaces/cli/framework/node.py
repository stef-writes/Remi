"""remi node — inspect nodes within an app."""

from __future__ import annotations

import asyncio
import json

import typer

from remi.infrastructure.loaders.yaml_loader import YamlAppLoader
from remi.interfaces.cli.shared import get_container, json_out, use_json
from remi.shared.ids import AppId, ModuleId

cmd = typer.Typer(name="node", help="Inspect nodes within an app.", no_args_is_help=True)


@cmd.command("list")
def list_nodes(
    path: str = typer.Argument(..., help="Path to app.yaml"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List all nodes in an app."""
    loader = YamlAppLoader()
    app_def = loader.load(path)
    if use_json(json_output):
        json_out({
            "app_id": app_def.app_id,
            "nodes": [
                {"id": m.id, "kind": m.kind, "description": m.description}
                for m in app_def.modules
            ],
        })
    else:
        typer.echo(f"Nodes in {app_def.metadata.name} ({len(app_def.modules)}):")
        for m in app_def.modules:
            desc = f" — {m.description}" if m.description else ""
            typer.echo(f"  - {m.id} ({m.kind}){desc}")


@cmd.command("info")
def info(
    path: str = typer.Argument(..., help="Path to app.yaml"),
    node_id: str = typer.Argument(..., help="Node ID to inspect"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Describe a specific node: kind, config, connections."""
    loader = YamlAppLoader()
    app_def = loader.load(path)

    module = None
    for m in app_def.modules:
        if m.id == node_id:
            module = m
            break

    if module is None:
        json_out({"ok": False, "error": f"Node '{node_id}' not found in app"})
        raise typer.Exit(1)

    incoming = [e.from_module for e in app_def.edges if e.to_module == node_id]
    outgoing = [e.to_module for e in app_def.edges if e.from_module == node_id]

    if use_json(json_output):
        json_out({
            "id": module.id,
            "kind": module.kind,
            "description": module.description,
            "config": module.config,
            "incoming_edges": incoming,
            "outgoing_edges": outgoing,
        })
    else:
        typer.echo(f"Node: {module.id}")
        typer.echo(f"Kind: {module.kind}")
        if module.description:
            typer.echo(f"Desc: {module.description}")
        typer.echo(f"Config: {json.dumps(module.config, indent=2, default=str)}")
        if incoming:
            typer.echo(f"Inputs from: {', '.join(incoming)}")
        if outgoing:
            typer.echo(f"Outputs to: {', '.join(outgoing)}")


@cmd.command("output")
def output(
    path: str = typer.Argument(..., help="Path to app.yaml"),
    run_id: str = typer.Argument(..., help="Run ID"),
    node_id: str = typer.Argument(..., help="Node ID"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Get the output of a specific node from a run."""
    asyncio.run(_output(path, run_id, node_id))


async def _output(path: str, run_id: str, node_id: str) -> None:
    container = get_container()
    loader = YamlAppLoader()
    app_def = loader.load(path)

    state = await container.state_query.get_module_state(
        AppId(app_def.app_id), run_id, ModuleId(node_id)
    )
    if state is None:
        json_out({"ok": False, "error": f"No output for node '{node_id}' in run '{run_id}'"})
        raise typer.Exit(1)

    json_out({
        "node_id": state.module_id,
        "status": state.status.value,
        "contract": state.contract,
        "output": state.output,
    })
