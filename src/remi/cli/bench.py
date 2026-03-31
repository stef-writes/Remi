"""remi bench — live benchmark for agent speed and intent routing.

Fires a suite of canned queries covering each intent category, captures
timing / tokens / cost / intent classification / tool usage per query,
and prints a Rich table comparing them.  One command, repeatable, gives
hard numbers before and after changes.

Usage:
    remi bench
    remi bench --mode agent --json
    remi bench --agent director --runs 3
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import typer

from remi.cli.shared import get_container_async, json_out, use_json

cmd = typer.Typer(name="bench", help="Benchmark agent speed and intent routing.", no_args_is_help=False)

BENCH_QUERIES: list[dict[str, str]] = [
    {"label": "greeting",    "expected_intent": "conversation", "query": "hi, what can you do?"},
    {"label": "lookup",      "expected_intent": "lookup",       "query": "how many vacant units are there?"},
    {"label": "analysis",    "expected_intent": "analysis",     "query": "compare delinquency rates across all managers"},
    {"label": "action",      "expected_intent": "action",       "query": "create action items for the manager with the worst delinquency"},
    {"label": "deep_dive",   "expected_intent": "deep_dive",    "query": "build a comprehensive delinquency trend report with breakdown by manager"},
]


@cmd.callback(invoke_without_command=True)
def bench(
    agent: str = typer.Option("director", "--agent", "-a", help="Agent to benchmark"),
    mode: str = typer.Option("agent", "--mode", "-m", help="Mode: ask or agent"),
    runs: int = typer.Option(1, "--runs", "-n", help="Runs per query (average)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output JSON"),
    queries: str = typer.Option("all", "--queries", "-q", help="Comma-separated labels or 'all'"),
) -> None:
    """Run canned queries and report timing, tokens, cost, and intent."""
    asyncio.run(_bench(agent, mode, runs, json_output, queries))


async def _bench(
    agent_name: str,
    mode: str,
    runs: int,
    fmt_json: bool,
    query_filter: str,
) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console(stderr=True)

    selected = BENCH_QUERIES
    if query_filter != "all":
        labels = {l.strip() for l in query_filter.split(",")}
        selected = [q for q in BENCH_QUERIES if q["label"] in labels]
        if not selected:
            typer.echo(f"No queries matched filter: {query_filter}", err=True)
            raise typer.Exit(1)

    console.print(f"\n[bold]REMI Agent Benchmark[/bold]  agent={agent_name}  mode={mode}  runs={runs}")
    console.print("[dim]Bootstrapping container…[/dim]")

    from remi.observability.logging import configure_logging
    configure_logging(level="WARNING", format="console")

    container = await get_container_async()
    session = await container.chat_session_store.create(agent_name)
    sandbox_id = f"bench-{session.id}"
    await container.sandbox.create_session(sandbox_id)

    results: list[dict[str, Any]] = []

    for qi, q in enumerate(selected, 1):
        label = q["label"]
        query = q["query"]
        expected = q["expected_intent"]

        run_results: list[dict[str, Any]] = []
        for run_i in range(runs):
            console.print(
                f"\n[cyan]({qi}/{len(selected)})[/cyan] "
                f"[bold]{label}[/bold]"
                + (f" run {run_i + 1}/{runs}" if runs > 1 else "")
            )
            console.print(f"  [dim]> {query}[/dim]")

            collected: dict[str, Any] = {
                "tools": [],
                "intent": None,
                "usage": None,
                "latency_ms": None,
                "cost": None,
                "model": None,
                "trace_id": None,
            }

            async def on_event(event_type: str, data: dict[str, Any]) -> None:
                if event_type == "tool_call":
                    tool_name = data.get("tool", "?")
                    collected["tools"].append(tool_name)
                    console.print(f"  [yellow]▶ {tool_name}[/yellow]")
                elif event_type == "done":
                    collected["intent"] = data.get("intent")
                    collected["usage"] = data.get("usage")
                    collected["latency_ms"] = data.get("latency_ms")
                    collected["cost"] = data.get("cost")
                    collected["model"] = data.get("model")
                    collected["trace_id"] = data.get("trace_id")

            t0 = time.monotonic()
            try:
                from remi.models.chat import Message

                user_msg = Message(role="user", content=query)
                await container.chat_session_store.append_message(session.id, user_msg)
                sess = await container.chat_session_store.get(session.id)
                assert sess is not None

                answer = await container.chat_agent.run_chat_agent(
                    agent_name,
                    sess.thread,
                    on_event,
                    sandbox_session_id=sandbox_id,
                    mode=mode,  # type: ignore[arg-type]
                )
                wall_ms = round((time.monotonic() - t0) * 1000)

                assistant_msg = Message(role="assistant", content=answer)
                await container.chat_session_store.append_message(session.id, assistant_msg)

                server_ms = collected["latency_ms"] or wall_ms
                usage = collected["usage"] or {}
                intent_match = "✓" if collected["intent"] == expected else "✗"

                run_result = {
                    "label": label,
                    "query": query,
                    "expected_intent": expected,
                    "actual_intent": collected["intent"],
                    "intent_match": intent_match,
                    "wall_ms": wall_ms,
                    "server_ms": server_ms,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "cost": collected["cost"],
                    "model": collected["model"],
                    "tool_count": len(collected["tools"]),
                    "tools": collected["tools"],
                    "trace_id": collected["trace_id"],
                    "answer_preview": (answer or "")[:120],
                }
                run_results.append(run_result)

                console.print(
                    f"  [green]✓[/green] {server_ms}ms  "
                    f"intent={collected['intent']} {intent_match}  "
                    f"tools={len(collected['tools'])}  "
                    f"tokens={usage.get('total_tokens', '?')}"
                )

            except Exception as exc:
                wall_ms = round((time.monotonic() - t0) * 1000)
                console.print(f"  [red]✗ Error after {wall_ms}ms:[/red] {exc}")
                run_results.append({
                    "label": label,
                    "query": query,
                    "expected_intent": expected,
                    "actual_intent": None,
                    "intent_match": "✗",
                    "wall_ms": wall_ms,
                    "server_ms": wall_ms,
                    "error": str(exc),
                })

        if runs > 1 and run_results:
            avg_ms = sum(r.get("server_ms", 0) for r in run_results) // len(run_results)
            avg_tokens = sum(r.get("total_tokens", 0) for r in run_results) // len(run_results)
            results.append({
                **run_results[0],
                "server_ms": avg_ms,
                "wall_ms": avg_ms,
                "total_tokens": avg_tokens,
                "runs": len(run_results),
            })
        elif run_results:
            results.append(run_results[0])

    await container.sandbox.destroy_session(sandbox_id)

    if fmt_json:
        json_out({"agent": agent_name, "mode": mode, "runs": runs, "results": results})
        return

    # Print summary table
    console.print()
    table = Table(
        title="[bold]Benchmark Results[/bold]",
        show_lines=True,
        title_style="bold cyan",
    )
    table.add_column("Query", style="bold", max_width=16)
    table.add_column("Intent", justify="center")
    table.add_column("Match", justify="center")
    table.add_column("Latency", justify="right", style="cyan")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Tools", justify="right")
    table.add_column("Model", max_width=20)

    for r in results:
        intent = r.get("actual_intent") or "—"
        match = "[green]✓[/green]" if r.get("intent_match") == "✓" else "[red]✗[/red]"
        latency = _fmt_ms(r.get("server_ms", 0))
        tokens = str(r.get("total_tokens", "—"))
        cost = f"${r['cost']:.4f}" if r.get("cost") else "—"
        tools = str(r.get("tool_count", 0))
        model = (r.get("model") or "—").replace("claude-", "").replace("-20250514", "")
        error = r.get("error")

        if error:
            table.add_row(r["label"], "[red]error[/red]", "✗", _fmt_ms(r.get("wall_ms", 0)), "—", "—", "—", f"[red]{error[:40]}[/red]")
        else:
            table.add_row(r["label"], intent, match, latency, tokens, cost, tools, model)

    console.print(table)

    total_ms = sum(r.get("server_ms", 0) for r in results if "error" not in r)
    total_cost = sum(r.get("cost", 0) or 0 for r in results if "error" not in r)
    total_tokens = sum(r.get("total_tokens", 0) for r in results if "error" not in r)
    console.print(
        f"\n[bold]Total:[/bold] {_fmt_ms(total_ms)}  "
        f"{total_tokens:,} tokens  "
        f"${total_cost:.4f}"
    )
    console.print()


def _fmt_ms(ms: int | float) -> str:
    if ms >= 60_000:
        return f"{ms / 60_000:.1f}m"
    if ms >= 1_000:
        return f"{ms / 1_000:.1f}s"
    return f"{ms:.0f}ms"
