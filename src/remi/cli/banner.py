"""Rich startup banner for ``remi serve``."""

from __future__ import annotations

import os
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from remi.config.settings import load_settings
from remi.shared.paths import APPS_DIR as AGENTS_DIR


def _key_status(env_var: str) -> Text:
    val = os.environ.get(env_var)
    if val:
        return Text(f"{val[:8]}...{val[-4:]}", style="green")
    return Text("NOT SET", style="bold red")


def _short_model(name: str) -> str:
    """Shorten model IDs for display: claude-sonnet-4-6-20260320 -> sonnet-4.6"""
    if name.startswith("claude-"):
        parts = name.replace("claude-", "").split("-")
        if len(parts) >= 3:
            return f"{parts[0]}-{parts[1]}.{parts[2]}"
    return name


def _load_agent_summary(agent_dir: str) -> dict[str, Any] | None:
    app_path = AGENTS_DIR / agent_dir / "app.yaml"
    if not app_path.exists():
        return None
    with open(app_path) as f:
        data = yaml.safe_load(f)
    for module in data.get("modules", []):
        if module.get("kind") == "agent":
            cfg = module.get("config", {})
            return {
                "name": agent_dir,
                "ask_tools": len(cfg.get("ask_tools", [])),
                "agent_tools": len(cfg.get("agent_tools", [])),
                "ask_model": _short_model(cfg.get("ask_model", "—")),
                "agent_model": _short_model(cfg.get("agent_model", "—")),
                "provider": cfg.get("provider", "—"),
            }
    return None


def print_banner(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    seed_demo: bool = False,
) -> None:
    """Print the startup banner to stderr via Rich."""
    console = Console(stderr=True)
    settings = load_settings()

    # ── Header ──
    header = Text()
    header.append("REMI", style="bold cyan")
    header.append("  Real Estate Management Intelligence\n", style="dim")
    header.append(f"v0.1.0  ·  {settings.environment}", style="dim")
    console.print(Panel(header, border_style="cyan", padding=(0, 2)))

    # ── Server ──
    server_table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
        title="Server",
        title_style="bold",
    )
    server_table.add_column(style="dim", width=16)
    server_table.add_column()
    server_table.add_row("API", f"http://{host}:{port}")
    server_table.add_row("WebSocket", f"ws://{host}:{port}/ws/chat")
    server_table.add_row("Frontend", "http://localhost:3000")
    server_table.add_row(
        "Options",
        ", ".join(
            filter(
                None,
                [
                    "reload" if reload else None,
                    "seed-demo" if seed_demo else None,
                ],
            )
        )
        or "none",
    )
    console.print(server_table)
    console.print()

    # ── LLM Configuration ──
    llm_table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
        title="LLM",
        title_style="bold",
    )
    llm_table.add_column(style="dim", width=16)
    llm_table.add_column()
    llm_table.add_row("Provider", settings.llm.default_provider)
    llm_table.add_row("Default Model", settings.llm.default_model)
    console.print(llm_table)
    console.print()

    # ── API Keys ──
    keys_table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
        title="API Keys",
        title_style="bold",
    )
    keys_table.add_column(style="dim", width=16)
    keys_table.add_column()
    keys_table.add_row("ANTHROPIC", _key_status("ANTHROPIC_API_KEY"))
    keys_table.add_row("OPENAI", _key_status("OPENAI_API_KEY"))
    keys_table.add_row("GOOGLE", _key_status("GOOGLE_API_KEY"))
    console.print(keys_table)
    console.print()

    # ── Agents ──
    agent_dirs = sorted(d.name for d in AGENTS_DIR.iterdir() if d.is_dir())
    if agent_dirs:
        agent_table = Table(
            box=None,
            padding=(0, 2),
            title="Agents",
            title_style="bold",
        )
        agent_table.add_column("Agent", style="cyan")
        agent_table.add_column("Provider")
        agent_table.add_column("Ask Model", no_wrap=True)
        agent_table.add_column("Agent Model", no_wrap=True)
        agent_table.add_column("Tools (ask/agent)", justify="right", no_wrap=True)

        for agent_dir in agent_dirs:
            info = _load_agent_summary(agent_dir)
            if info:
                agent_table.add_row(
                    info["name"],
                    str(info["provider"]),
                    str(info["ask_model"]),
                    str(info["agent_model"]),
                    f"{info['ask_tools']} / {info['agent_tools']}",
                )
        console.print(agent_table)
        console.print()

    # ── Storage ──
    storage_table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
        title="Storage",
        title_style="bold",
    )
    storage_table.add_column(style="dim", width=16)
    storage_table.add_column()
    storage_table.add_row("Backend", settings.state_store.backend)
    storage_table.add_row(
        "Embeddings", f"{settings.embeddings.provider}/{settings.embeddings.model}"
    )
    storage_table.add_row("Logging", f"{settings.logging.level} / {settings.logging.format}")
    console.print(storage_table)
    console.print()

    console.print(
        Text("Starting uvicorn...", style="dim italic"),
    )
