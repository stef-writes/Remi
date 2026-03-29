"""remi app — manage and run apps."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import typer

from remi.infrastructure.loaders.yaml_loader import YamlAppLoader

if TYPE_CHECKING:
    from remi.domain.graph.definitions import AppDefinition
    from remi.infrastructure.config.container import InclineContainer
from remi.interfaces.cli.shared import get_container, json_out, parse_params, use_json
from remi.shared.ids import AppId, ModuleId

cmd = typer.Typer(name="app", help="Manage and run apps.", no_args_is_help=True)


@cmd.command("validate")
def validate(
    path: str = typer.Argument(..., help="Path to app.yaml"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Validate an app definition without registering it."""
    container = get_container()
    loader = YamlAppLoader()
    try:
        app_def = loader.load(path)
    except Exception as exc:
        json_out({"ok": False, "error": str(exc)})
        raise typer.Exit(1) from None

    result = container.validate_app_uc.execute(app_def)
    if result.is_err:
        json_out({"ok": False, "errors": result.unwrap_err()})
        raise typer.Exit(1)

    if use_json(json_output):
        json_out({"ok": True, "app_id": app_def.app_id, "name": app_def.metadata.name})
    else:
        typer.echo(f"Valid: {app_def.metadata.name} ({app_def.app_id})")


@cmd.command("run")
def run(
    path: str = typer.Argument(..., help="Path to app.yaml"),
    param: list[str] = typer.Option([], "--param", "-p", help="key=value pairs"),
    start_from: str | None = typer.Option(None, help="Module ID to start from"),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Module ID whose output to print"
    ),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Load and execute an app graph, returning structured output."""
    asyncio.run(_run(path, param, start_from, output, use_json(json_output)))


async def _run(
    path: str,
    raw_params: list[str],
    start_from: str | None,
    output_module: str | None,
    fmt_json: bool,
) -> None:
    container = get_container()
    loader = YamlAppLoader()

    try:
        app_def = loader.load(path)
    except Exception as exc:
        json_out({"ok": False, "error": str(exc)})
        raise typer.Exit(1) from None

    reg_result = container.register_app_uc.execute(app_def)
    if reg_result.is_err:
        json_out({"ok": False, "errors": reg_result.unwrap_err()})
        raise typer.Exit(1)

    run_params = parse_params(raw_params)
    sf = ModuleId(start_from) if start_from else None

    result = await container.run_app_uc.execute(
        AppId(app_def.app_id),
        start_from=sf,
        run_params=run_params or None,
    )

    outputs = await _collect_outputs(container, app_def, result.run_id, output_module)

    if fmt_json:
        json_out({
            "ok": result.status.value == "completed",
            "run_id": result.run_id,
            "status": result.status.value,
            "errors": result.errors,
            "outputs": outputs,
        })
    else:
        typer.echo(f"Run {result.run_id}: {result.status.value}")
        if result.errors:
            for error in result.errors:
                typer.echo(f"  Error: {error}", err=True)
        else:
            for mid, data in outputs.items():
                typer.echo(f"\n[{mid}] contract={data.get('contract', '?')}")
                typer.echo(json.dumps(data.get("output"), indent=2, default=str))

    if result.errors:
        raise typer.Exit(1)


@cmd.command("info")
def info(
    path: str = typer.Argument(..., help="Path to app.yaml"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Display summary info about an app definition."""
    loader = YamlAppLoader()
    try:
        app_def = loader.load(path)
    except Exception as exc:
        json_out({"ok": False, "error": str(exc)})
        raise typer.Exit(1) from None

    if use_json(json_output):
        json_out({
            "app_id": app_def.app_id,
            "name": app_def.metadata.name,
            "version": app_def.metadata.version,
            "modules": [{"id": m.id, "kind": m.kind} for m in app_def.modules],
            "edges": [
                {"from": e.from_module, "to": e.to_module, "condition": e.condition}
                for e in app_def.edges
            ],
        })
    else:
        typer.echo(f"App:     {app_def.metadata.name}")
        typer.echo(f"ID:      {app_def.app_id}")
        typer.echo(f"Version: {app_def.metadata.version}")
        typer.echo(f"Modules: {len(app_def.modules)}")
        typer.echo(f"Edges:   {len(app_def.edges)}")
        if app_def.modules:
            typer.echo("\nModules:")
            for m in app_def.modules:
                typer.echo(f"  - {m.id} ({m.kind})")
        if app_def.edges:
            typer.echo("\nEdges:")
            for e in app_def.edges:
                cond = f" [if {e.condition}]" if e.condition else ""
                typer.echo(f"  - {e.from_module} -> {e.to_module}{cond}")


@cmd.command("inspect")
def inspect(
    path: str = typer.Argument(..., help="Path to app.yaml"),
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    module: str | None = typer.Option(None, "--module", "-m"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Inspect the state of a completed or failed run."""
    asyncio.run(_inspect(path, run_id, module, use_json(json_output)))


async def _inspect(
    path: str, run_id: str, module_id: str | None, fmt_json: bool
) -> None:
    container = get_container()
    loader = YamlAppLoader()
    app_def = loader.load(path)

    if module_id:
        state = await container.state_query.get_module_state(
            AppId(app_def.app_id), run_id, ModuleId(module_id)
        )
        if state is None:
            json_out({"ok": False, "error": f"No state for module {module_id}"})
            raise typer.Exit(1)
        json_out({
            "module_id": state.module_id,
            "status": state.status.value,
            "contract": state.contract,
            "output": state.output,
        })
    else:
        records = await container.state_query.get_run_history(
            AppId(app_def.app_id), run_id
        )
        run_record = await container.state_query.get_run_record(
            AppId(app_def.app_id), run_id
        )
        json_out({
            "run_id": run_id,
            "status": run_record.status.value if run_record else "unknown",
            "module_count": run_record.module_count if run_record else 0,
            "completed_count": run_record.completed_count if run_record else 0,
            "failed_count": run_record.failed_count if run_record else 0,
            "modules": [
                {
                    "module_id": r.module_id,
                    "status": r.status.value,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for r in records
            ],
        })


@cmd.command("list")
def list_apps(
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List all registered apps."""
    container = get_container()
    apps = container.app_registry.list_apps()
    if use_json(json_output):
        json_out({
            "apps": [
                {
                    "app_id": a.app_id,
                    "name": a.metadata.name,
                    "version": a.metadata.version,
                }
                for a in apps
            ]
        })
    else:
        if not apps:
            typer.echo("No apps registered.")
            return
        typer.echo(f"Registered apps ({len(apps)}):")
        for a in apps:
            typer.echo(f"  - {a.app_id}: {a.metadata.name} v{a.metadata.version}")


async def _collect_outputs(
    container: InclineContainer,
    app_def: AppDefinition,
    run_id: str,
    target_module: str | None,
) -> dict[str, Any]:
    if target_module:
        module_ids = [ModuleId(target_module)]
    else:
        all_sources = {e.from_module for e in app_def.edges}
        terminal_ids = [m.id for m in app_def.modules if m.id not in all_sources]
        module_ids = terminal_ids or [m.id for m in app_def.modules]

    outputs: dict[str, Any] = {}
    for mid in module_ids:
        state = await container.state_query.get_module_state(
            AppId(app_def.app_id), run_id, mid
        )
        if state:
            outputs[mid] = {
                "contract": state.contract,
                "status": state.status.value,
                "output": state.output,
            }
    return outputs
