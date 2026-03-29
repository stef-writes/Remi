"""remi provider — manage and test LLM providers."""

from __future__ import annotations

import asyncio

import typer

from remi.interfaces.cli.shared import get_container, json_out, use_json

cmd = typer.Typer(name="provider", help="Manage LLM providers.", no_args_is_help=True)


@cmd.command("list")
def list_providers(
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List available LLM providers (auto-detected from installed packages)."""
    container = get_container()
    providers = container.provider_factory.available()
    if use_json(json_output):
        json_out({"providers": providers})
    else:
        if not providers:
            typer.echo("No LLM providers available.")
            return
        typer.echo("Available providers:")
        for p in providers:
            typer.echo(f"  - {p}")


@cmd.command("test")
def test(
    name: str = typer.Argument(..., help="Provider name (e.g. openai, anthropic)"),
    model: str = typer.Option(..., "--model", "-m", help="Model to test"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Test a provider connection with a simple completion."""
    asyncio.run(_test(name, model))


async def _test(name: str, model: str) -> None:
    from remi.domain.modules.base import Message

    container = get_container()
    try:
        provider = container.provider_factory.create(name)
    except ValueError as exc:
        json_out({"ok": False, "error": str(exc)})
        raise typer.Exit(1) from None

    try:
        resp = await provider.complete(
            model=model,
            messages=[Message(role="user", content="Say 'hello' in one word.")],
            max_tokens=10,
        )
        json_out({
            "ok": True,
            "provider": name,
            "model": resp.model,
            "content": resp.content,
            "usage": resp.usage,
        })
    except Exception as exc:
        json_out({"ok": False, "provider": name, "model": model, "error": str(exc)})
        raise typer.Exit(1) from None
