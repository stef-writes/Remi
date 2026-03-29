"""remi tool — discover and invoke tools."""

from __future__ import annotations

import asyncio

import typer

from remi.interfaces.cli.shared import get_container, json_out, parse_params, use_json

cmd = typer.Typer(name="tool", help="Discover and invoke tools.", no_args_is_help=True)


@cmd.command("list")
def list_tools(
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List all available tools.

    Tools are discovered from the runtime environment — what's registered
    depends on the app context, installed connectors, and active sources.
    """
    container = get_container()
    tools = container.tool_registry.list_tools()
    if use_json(json_output):
        json_out({
            "tools": [
                {"name": t.name, "description": t.description}
                for t in tools
            ]
        })
    else:
        if not tools:
            typer.echo("No tools available.")
            return
        for t in tools:
            typer.echo(t.to_help_text())
            typer.echo()


@cmd.command("info")
def info(
    name: str = typer.Argument(..., help="Tool name"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Describe a tool — equivalent to --help for a tool.

    Returns a human-and-agent readable description of what the tool does
    and what arguments it accepts. Parameters come from the runtime
    environment, not a static schema.
    """
    container = get_container()
    entry = container.tool_registry.get(name)
    if entry is None:
        json_out({"ok": False, "error": f"Tool '{name}' not found"})
        raise typer.Exit(1)

    _, defn = entry
    if use_json(json_output):
        json_out({
            "name": defn.name,
            "description": defn.description,
            "args": [
                {
                    "name": a.name,
                    "description": a.description,
                    "required": a.required,
                    "type": a.type,
                }
                for a in defn.args
            ],
        })
    else:
        typer.echo(defn.to_help_text())


@cmd.command("run")
def run(
    name: str = typer.Argument(..., help="Tool name"),
    arg: list[str] = typer.Option([], "--arg", "-a", help="key=value argument pairs"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Invoke a tool directly with arguments."""
    asyncio.run(_run(name, arg))


async def _run(name: str, raw_args: list[str]) -> None:
    container = get_container()
    entry = container.tool_registry.get(name)
    if entry is None:
        json_out({"ok": False, "error": f"Tool '{name}' not found"})
        raise typer.Exit(1)

    fn, _ = entry
    args = parse_params(raw_args)
    result = await fn(args)
    json_out({"ok": True, "tool": name, "result": result})
