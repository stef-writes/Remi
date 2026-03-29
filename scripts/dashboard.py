#!/usr/bin/env python3
"""REMI Knowledge Physics Dashboard.

A unified Textual TUI that shows the live state of the knowledge system
alongside a real-time agent chat feed — all in one place.

Layout:
  ┌───────────────────────┬─────────────────────────────────────────┐
  │  SIGNALS  (left)      │  ACTIVITY LOG  (top-right)              │
  │  Severity breakdown   │  Pipeline phases, entailment spans,     │
  │  Per-signal list      │  tool calls, trace events               │
  ├───────────────────────┤─────────────────────────────────────────┤
  │  TBOX  (bottom-left)  │  CHAT FEED  (bottom-right)              │
  │  Signal defs          │  you> / remi> REPL with live tool feed  │
  │  Thresholds           │                                         │
  └───────────────────────┴─────────────────────────────────────────┘
  Status bar: agent · model · perception · trace id · run/quit help

Run from the project root:
    uv run python scripts/dashboard.py
    uv run python scripts/dashboard.py --agent director --verbose
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

# Ensure src is on the path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    Log,
    RichLog,
    Static,
)

# ── severity palette ──────────────────────────────────────────────────────────
SEV_COLOR = {
    "critical": "red",
    "high": "bright_red",
    "medium": "yellow",
    "low": "dim",
}
SEV_ICON = {
    "critical": "[red]●[/red]",
    "high": "[bright_red]●[/bright_red]",
    "medium": "[yellow]●[/yellow]",
    "low": "[dim]●[/dim]",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _ts(started: float) -> str:
    return f"{time.monotonic() - started:6.1f}s"


# ── Panels ────────────────────────────────────────────────────────────────────

class SignalPanel(Static):
    """Left-top: live signal list with severity breakdown."""

    DEFAULT_CSS = """
    SignalPanel {
        border: round $primary;
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    """

    def render(self) -> str:  # overridden dynamically via update()
        return self._content

    def __init__(self) -> None:
        super().__init__()
        self._content = "[dim]No signals yet — run pipeline[/dim]"

    def refresh_signals(self, signals: list[Any], domain: Any | None) -> None:
        if not signals:
            self._content = "[dim]No active signals[/dim]"
            self.refresh()
            return

        breakdown: dict[str, int] = {}
        for s in signals:
            sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
            breakdown[sev] = breakdown.get(sev, 0) + 1

        lines: list[str] = []
        for sev in ("critical", "high", "medium", "low"):
            if cnt := breakdown.get(sev, 0):
                lines.append(f"{SEV_ICON.get(sev, '?')} {cnt} {sev}")

        lines.append("")
        for s in signals:
            sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
            icon = SEV_ICON.get(sev, "?")
            lines.append(
                f"{icon} [{SEV_COLOR.get(sev, 'white')}]{_truncate(s.signal_type, 28)}[/]"
            )
            lines.append(f"   [dim]{_truncate(s.entity_name, 32)}[/dim]")
            lines.append(f"   [dim]{_truncate(s.description, 44)}[/dim]")
            lines.append("")

        self._content = "\n".join(lines)
        self.refresh()


class TBoxPanel(Static):
    """Left-bottom: domain ontology summary (TBox)."""

    DEFAULT_CSS = """
    TBoxPanel {
        border: round $secondary;
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._content = "[dim]TBox not loaded[/dim]"

    def render(self) -> str:
        return self._content

    def refresh_tbox(self, domain: Any) -> None:
        lines: list[str] = [f"[bold cyan]{len(domain.signals)} signal definitions[/bold cyan]"]
        for name, defn in list(domain.signals.items())[:12]:
            sev = defn.severity.value if hasattr(defn.severity, "value") else str(defn.severity)
            icon = SEV_ICON.get(sev, "?")
            lines.append(f"  {icon} [dim]{_truncate(name, 30)}[/dim]")

        if domain.thresholds:
            lines += ["", f"[bold cyan]{len(domain.thresholds)} thresholds[/bold cyan]"]
            for k, v in list(domain.thresholds.items())[:8]:
                lines.append(f"  [dim]{_truncate(k, 24)}[/dim] = {v}")

        if domain.policies:
            lines += ["", f"[bold cyan]{len(domain.policies)} policies[/bold cyan]"]
            for p in domain.policies[:4]:
                tag = p.deontic.value.upper() if hasattr(p.deontic, "value") else str(p.deontic)
                lines.append(f"  [{tag}] [dim]{_truncate(p.description, 36)}[/dim]")

        if domain.causal_chains:
            lines.append(f"\n[bold cyan]{len(domain.causal_chains)} causal chains[/bold cyan]")

        self._content = "\n".join(lines)
        self.refresh()


# ── Main App ─────────────────────────────────────────────────────────────────

class RemiDashboard(App):
    """REMI Knowledge Physics Dashboard."""

    TITLE = "REMI — Knowledge Physics"
    SUB_TITLE = "live · knowledge · signals · agent"

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-row {
        height: 1fr;
        layout: horizontal;
    }
    #left-col {
        width: 40;
        layout: vertical;
    }
    #right-col {
        width: 1fr;
        layout: vertical;
    }
    #signal-panel-title {
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
    }
    #tbox-title {
        height: 1;
        background: $secondary;
        color: $text;
        text-align: center;
    }
    #activity-title {
        height: 1;
        background: $accent;
        color: $text;
        text-align: center;
    }
    #chat-title {
        height: 1;
        background: $surface;
        color: $text;
        text-align: center;
    }
    #activity-log {
        height: 1fr;
        border: round $accent;
    }
    #chat-log {
        height: 1fr;
        border: round $success;
    }
    #chat-input {
        height: 3;
        border: round $success;
        margin: 0;
    }
    """

    BINDINGS = [
        Binding("r", "run_pipeline", "Run pipeline", show=True),
        Binding("ctrl+c", "quit", "Quit", show=True),
    ]

    signal_count: reactive[int] = reactive(0)
    trace_id: reactive[str] = reactive("")

    def __init__(
        self,
        agent_name: str = "director",
        verbose: bool = False,
    ) -> None:
        super().__init__()
        self._agent_name = agent_name
        self._verbose = verbose
        self._container: Any = None
        self._session_id: str | None = None
        self._sandbox_session_id: str | None = None
        self._started_at = time.monotonic()
        self._llm_count = 0
        self._tool_count = 0

    # ── compose ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-row"):
            with Vertical(id="left-col"):
                yield Label(" ◆ SIGNALS ", id="signal-panel-title")
                yield SignalPanel(id="signal-panel")  # type: ignore[call-arg]
                yield Label(" ◆ TBOX ", id="tbox-title")
                yield TBoxPanel(id="tbox-panel")  # type: ignore[call-arg]
            with Vertical(id="right-col"):
                yield Label(" ◆ ACTIVITY LOG ", id="activity-title")
                yield RichLog(id="activity-log", highlight=True, markup=True, wrap=True)
                yield Label(" ◆ AGENT CHAT ", id="chat-title")
                yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
                yield Input(
                    placeholder="you>  ask anything… (r = re-run pipeline, ctrl+c = quit)",
                    id="chat-input",
                )
        yield Footer()

    # ── lifecycle ──────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._boot()

    @work(exclusive=True, thread=False)
    async def _boot(self) -> None:
        self._activity("  [dim]Bootstrapping container…[/dim]")
        from remi.infrastructure.config.container import Container
        from remi.infrastructure.config.settings import load_settings
        from remi.infrastructure.observability.logging import configure_logging

        settings = load_settings()
        configure_logging(level="WARNING", format="text")
        self._container = Container(settings)
        await self._container.ensure_bootstrapped()
        self._activity("  [green]✓[/green] Container bootstrapped")

        # Sandbox
        from remi.infrastructure.sandbox.seeder import SandboxSeeder  # noqa: F401

        session = await self._container.chat_session_store.create(self._agent_name)
        self._session_id = session.id
        self._sandbox_session_id = f"dash-{session.id}"
        await self._container.sandbox.create_session(self._sandbox_session_id)
        seeded = await self._container.sandbox_seeder.seed(
            self._container.sandbox, self._sandbox_session_id
        )
        self._activity(f"  [green]✓[/green] Sandbox ready — {len(seeded)} data files")

        # Initial TBox
        self._refresh_tbox()

        # Auto-run pipeline on startup
        await self._run_pipeline_async()

    # ── pipeline ──────────────────────────────────────────────────────────

    def action_run_pipeline(self) -> None:
        if self._container is None:
            return
        self._run_pipeline_work()

    @work(exclusive=True, thread=False)
    async def _run_pipeline_work(self) -> None:
        await self._run_pipeline_async()

    async def _run_pipeline_async(self) -> None:
        if self._container is None:
            return
        self._activity("\n[bold cyan]── Signal Pipeline ──[/bold cyan]")
        try:
            result = await self._container.signal_pipeline.run_all()
            self._activity(
                f"  [green]✓[/green] {result.produced} signal(s) produced"
            )
            for source, pr in result.per_source.items():
                self._activity(
                    f"    [dim]{source}:[/dim] {pr.produced} signals, {pr.errors} err"
                )
            if result.trace_id:
                self.trace_id = result.trace_id
                self._activity(f"  [cyan]trace[/cyan] {result.trace_id}")
                await self._show_trace_spans(result.trace_id)

            # Refresh signal panel
            signals = await self._container.signal_store.list_signals()
            self.signal_count = len(signals)
            self.query_one("#signal-panel", SignalPanel).refresh_signals(
                signals, self._container.domain_ontology
            )
        except Exception as exc:
            self._activity(f"  [red]✗ Pipeline error:[/red] {exc}")

    async def _show_trace_spans(self, trace_id: str) -> None:
        try:
            spans = await self._container.trace_store.list_spans(trace_id)
            self._activity(
                f"  [cyan]{len(spans)} trace spans[/cyan] — "
                f"[dim]remi trace show {trace_id}[/dim]"
            )
            for span in spans[:10]:
                dur = f"{span.duration_ms:.0f}ms" if span.duration_ms else "…"
                status_icon = (
                    "[green]✓[/green]" if span.status.value == "ok" else "[red]✗[/red]"
                )
                self._activity(
                    f"    {status_icon} [dim]{span.kind.value:12s}[/dim] "
                    f"{_truncate(span.name, 36)}  [dim]{dur}[/dim]"
                )
            if len(spans) > 10:
                self._activity(f"    [dim]… {len(spans) - 10} more spans[/dim]")
        except Exception:
            pass

    # ── TBox ──────────────────────────────────────────────────────────────

    def _refresh_tbox(self) -> None:
        if self._container is None:
            return
        try:
            self.query_one("#tbox-panel", TBoxPanel).refresh_tbox(
                self._container.domain_ontology
            )
        except (NoMatches, Exception):
            pass

    # ── chat ──────────────────────────────────────────────────────────────

    @on(Input.Submitted, "#chat-input")
    def on_chat_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self.query_one("#chat-input", Input).value = ""
        if self._container is None or self._session_id is None:
            self._chat("[red]Container not ready yet.[/red]")
            return
        self._run_chat(text)

    @work(exclusive=False, thread=False)
    async def _run_chat(self, user_input: str) -> None:
        from remi.domain.modules.base import Message

        self._chat(f"\n[bold green]you>[/bold green] {user_input}")

        # Show perception snapshot
        try:
            signals = await self._container.signal_store.list_signals()
            sev_parts: list[str] = []
            breakdown: dict[str, int] = {}
            for s in signals:
                sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
                breakdown[sev] = breakdown.get(sev, 0) + 1
            for sev in ("critical", "high", "medium", "low"):
                if cnt := breakdown.get(sev, 0):
                    sev_parts.append(f"{SEV_ICON.get(sev, '?')} {cnt}")
            sev_str = "  ".join(sev_parts) if sev_parts else "none"
            self._chat(
                f"  [cyan]◆ perception[/cyan]  tbox ✓  signals: {sev_str}"
            )
        except Exception:
            pass

        user_msg = Message(role="user", content=user_input)
        await self._container.chat_session_store.append_message(self._session_id, user_msg)
        session = await self._container.chat_session_store.get(self._session_id)
        assert session is not None

        started = time.monotonic()
        self._tool_count = 0
        self._llm_count = 0

        async def on_event(event_type: str, data: dict[str, Any]) -> None:
            elapsed = f"{time.monotonic() - started:5.1f}s"
            ts = f"[dim]{elapsed}[/dim]"

            if event_type == "tool_call":
                self._tool_count += 1
                tool = data.get("tool", "?")
                args = data.get("arguments", {})
                args_str = "  ".join(
                    f"[dim]{k}=[/dim]{_truncate(str(v), 30)}"
                    for k, v in list(args.items())[:2]
                )
                self._chat(f"  {ts}  [yellow]▶ {tool}[/yellow]  {args_str}")
                self._activity(f"  {ts}  [yellow]▶ {tool}[/yellow]  {args_str}")

            elif event_type == "tool_result":
                tool = data.get("tool", "?")
                result = data.get("result", "")
                preview = _truncate(str(result), 80)
                self._chat(f"  {ts}  [green]◀ {tool}[/green]  [dim]{preview}[/dim]")
                self._activity(f"  {ts}  [green]◀ {tool}[/green]  [dim]{preview}[/dim]")

            elif event_type == "delta":
                iteration = data.get("iteration", 0)
                self._llm_count = iteration + 1
                if self._verbose:
                    content = data.get("content", "")
                    if content:
                        self._chat(
                            f"  {ts}  [blue]◇[/blue] [dim]{_truncate(str(content), 80)}[/dim]"
                        )

            elif event_type == "error":
                error = data.get("error", "unknown")
                self._chat(f"  {ts}  [red]✗[/red] {error}")

        try:
            answer = await self._container.chat_agent.run_chat_agent(
                self._agent_name,
                session.thread,
                on_event,
                sandbox_session_id=self._sandbox_session_id,
            )
        except Exception as exc:
            self._chat(f"  [red]✗ Error:[/red] {exc}")
            return

        elapsed = time.monotonic() - started
        self._chat(
            f"\n[bold cyan]remi>[/bold cyan] {answer}"
            f"\n  [dim]{elapsed:.1f}s  ·  {self._llm_count} LLM  ·  {self._tool_count} tools[/dim]"
        )

        assistant_msg = Message(role="assistant", content=answer)
        await self._container.chat_session_store.append_message(self._session_id, assistant_msg)

        # After each chat turn, refresh signals (agent may have run entailment)
        try:
            signals = await self._container.signal_store.list_signals()
            if len(signals) != self.signal_count:
                self.signal_count = len(signals)
                self.query_one("#signal-panel", SignalPanel).refresh_signals(
                    signals, self._container.domain_ontology
                )
        except Exception:
            pass

    # ── write helpers ─────────────────────────────────────────────────────

    def _activity(self, msg: str) -> None:
        try:
            self.query_one("#activity-log", RichLog).write(msg)
        except NoMatches:
            pass

    def _chat(self, msg: str) -> None:
        try:
            self.query_one("#chat-log", RichLog).write(msg)
        except NoMatches:
            pass

    # ── cleanup ───────────────────────────────────────────────────────────

    async def on_unmount(self) -> None:
        if self._container is not None and self._sandbox_session_id is not None:
            try:
                await self._container.sandbox.destroy_session(self._sandbox_session_id)
            except Exception:
                pass


# ── Entry point ───────────────────────────────────────────────────────────────

def run(agent: str = "director", verbose: bool = False) -> None:
    RemiDashboard(agent_name=agent, verbose=verbose).run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="REMI Knowledge Physics Dashboard")
    parser.add_argument("--agent", default="director", help="Agent to chat with")
    parser.add_argument("--verbose", action="store_true", help="Show LLM token deltas")
    args = parser.parse_args()
    run(agent=args.agent, verbose=args.verbose)
