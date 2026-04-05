"""Live terminal display for agent activity.

Renders a real-time feed of everything the agent does: perception loading,
LLM calls, tool invocations, reasoning output, and trace summaries.
Uses rich for styled terminal output with spinners and panels.
"""

from __future__ import annotations

import contextlib
import json
import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table


class LiveAgentDisplay:
    """Collects agent events and renders them to the terminal in real-time."""

    def __init__(self, console: Console | None = None, verbose: bool = False) -> None:
        self._console = console or Console(stderr=True)
        self._verbose = verbose
        self._events: list[dict[str, Any]] = []
        self._started_at = time.monotonic()
        self._tool_count = 0
        self._llm_count = 0
        self._current_tool: str | None = None
        self._perception_loaded = False
        self._signal_count = 0

    async def on_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Callback wired into AgentNode's on_event."""
        elapsed = time.monotonic() - self._started_at
        self._events.append({"type": event_type, "data": data, "elapsed": elapsed})
        self._render_event(event_type, data, elapsed)

    def show_perception(
        self,
        tbox_injected: bool,
        signal_count: int,
        severity_breakdown: dict[str, int] | None = None,
    ) -> None:
        """Called before the agent loop starts to show what was perceived."""
        self._perception_loaded = True
        self._signal_count = signal_count

        self._console.print()
        self._console.print(Rule("[bold cyan]Perception[/bold cyan]", style="cyan"))

        if tbox_injected:
            self._console.print("  [cyan]◆[/cyan] TBox world model injected")

        if signal_count > 0:
            sev_parts = []
            if severity_breakdown:
                for sev, count in sorted(severity_breakdown.items()):
                    icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(
                        sev, "❓"
                    )
                    sev_parts.append(f"{icon} {count} {sev}")
            sev_str = "  ".join(sev_parts) if sev_parts else ""
            self._console.print(f"  [cyan]◆[/cyan] {signal_count} active signals  {sev_str}")
        else:
            self._console.print("  [dim]No active signals[/dim]")

        self._console.print()

    def show_sandbox_ready(self, session_id: str, files: list[str]) -> None:
        """Display sandbox initialization banner."""
        self._console.print(f"  [cyan]◆[/cyan] Sandbox ready — {len(files)} data files loaded")

    def show_start(self, agent_name: str, model: str, provider: str) -> None:
        self._console.print(
            Panel(
                f"[bold]{agent_name}[/bold]  [dim]{provider}/{model}[/dim]",
                title="[bold green]Agent Started[/bold green]",
                border_style="green",
            )
        )

    def show_done(self, trace_id: str | None = None) -> None:
        elapsed = time.monotonic() - self._started_at

        summary = Table.grid(padding=(0, 2))
        summary.add_column(style="dim")
        summary.add_column()
        summary.add_row("Duration", f"{elapsed:.1f}s")
        summary.add_row("LLM calls", str(self._llm_count))
        summary.add_row("Tool calls", str(self._tool_count))
        if self._signal_count:
            summary.add_row("Signals active", str(self._signal_count))
        if trace_id:
            summary.add_row("Trace", trace_id)
            summary.add_row("Inspect", f"[dim]remi trace show {trace_id}[/dim]")

        self._console.print()
        self._console.print(Panel(summary, title="[bold]Run Complete[/bold]", border_style="green"))

    def _render_event(self, event_type: str, data: dict[str, Any], elapsed: float) -> None:
        ts = f"[dim]{elapsed:6.1f}s[/dim]"

        if event_type == "tool_call":
            self._tool_count += 1
            tool = data.get("tool", "?")
            args = data.get("arguments", {})
            self._current_tool = tool

            if tool == "sandbox_exec_python":
                self._render_sandbox_call(ts, args)
            else:
                args_preview = _format_args(args)
                self._console.print(f"  {ts}  [yellow]▶ {tool}[/yellow]  {args_preview}")

        elif event_type == "tool_result":
            tool = data.get("tool", "?")
            result = data.get("result", "")

            if tool == "sandbox_exec_python":
                self._render_sandbox_result(ts, result)
            else:
                preview = _truncate_str(str(result), 120)
                self._console.print(f"  {ts}  [green]◀ {tool}[/green]  [dim]{preview}[/dim]")
            self._current_tool = None

        elif event_type == "delta":
            content = data.get("content", "")
            iteration = data.get("iteration", 0)
            self._llm_count = iteration + 1
            if self._verbose and content:
                for line in str(content).split("\n")[:3]:
                    self._console.print(f"  {ts}  [blue]◇[/blue] {_truncate_str(line, 100)}")

        elif event_type == "done":
            pass

        elif event_type == "error":
            error = data.get("error", "unknown error")
            self._console.print(f"  {ts}  [red]✗ Error:[/red] {error}")

    def _render_sandbox_call(self, ts: str, args: dict[str, Any]) -> None:
        code = args.get("code", "")
        self._console.print(f"  {ts}  [yellow]▶ sandbox_exec_python[/yellow]")
        if code:
            syntax = Syntax(
                code.strip(),
                "python",
                theme="monokai",
                line_numbers=True,
                padding=1,
            )
            self._console.print(Panel(syntax, border_style="yellow", expand=False))

    def _render_sandbox_result(self, ts: str, result: Any) -> None:
        if isinstance(result, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                result = json.loads(result)

        if isinstance(result, dict):
            status = result.get("status", "")
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            duration = result.get("duration_ms", 0)

            status_style = "green" if status == "success" else "red"
            self._console.print(
                f"  {ts}  [{status_style}]◀ sandbox[/{status_style}]  "
                f"[dim]{status} in {duration:.0f}ms[/dim]"
            )

            if stdout:
                for line in stdout.split("\n")[:10]:
                    self._console.print(f"         [dim]│[/dim] {line}")
                if stdout.count("\n") > 10:
                    self._console.print(
                        f"         [dim]│ ... ({stdout.count(chr(10)) - 10} more lines)[/dim]"
                    )

            if stderr:
                for line in stderr.split("\n")[:5]:
                    self._console.print(f"         [red]│ {line}[/red]")
        else:
            preview = _truncate_str(str(result), 120)
            self._console.print(f"  {ts}  [green]◀ sandbox[/green]  [dim]{preview}[/dim]")


def _format_args(args: dict[str, Any]) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        v_str = str(v)
        if len(v_str) > 40:
            v_str = v_str[:37] + "..."
        parts.append(f"[dim]{k}=[/dim]{v_str}")
    return "  ".join(parts[:3])


def _truncate_str(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
