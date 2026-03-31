"""remi chat — interactive conversational REPL with REMI agents."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from remi.cli.shared import get_container_async

cmd = typer.Typer(name="chat", help="Interactive chat with REMI agents.", no_args_is_help=False)


@cmd.callback(invoke_without_command=True)
def chat_repl(
    agent: str = typer.Option("director", "--agent", "-a", help="Agent to chat with"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show LLM output tokens live"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output, no live feed"),
) -> None:
    """Start an interactive chat session with a REMI agent."""
    asyncio.run(_run_repl(agent, verbose=verbose, quiet=quiet))


async def _run_repl(agent_name: str, verbose: bool = False, quiet: bool = False) -> None:
    from remi.cli.live_display import LiveAgentDisplay
    from remi.models.chat import Message

    container = await get_container_async()
    session = await container.chat_session_store.create(agent_name)

    sandbox_session_id = f"chat-{session.id}"
    await container.sandbox.create_session(sandbox_session_id)

    typer.echo(f"REMI Chat — agent: {agent_name} | session: {session.id}")
    typer.echo("Type your question and press Enter. Use /quit to exit.\n")

    try:
        while True:
            try:
                user_input = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                typer.echo("\nGoodbye!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("/quit", "/exit", "/q"):
                typer.echo("Goodbye!")
                break

            user_msg = Message(role="user", content=user_input)
            await container.chat_session_store.append_message(session.id, user_msg)

            session_latest = await container.chat_session_store.get(session.id)
            assert session_latest is not None

            display = LiveAgentDisplay(verbose=verbose)

            if quiet:

                async def on_event(event_type: str, data: dict[str, Any]) -> None:
                    if event_type == "tool_call":
                        typer.echo(f"  [calling {data.get('tool', '?')}...]", err=True)
            else:
                on_event = display.on_event  # type: ignore[assignment]

            if not quiet:
                signal_count = 0
                severity_breakdown: dict[str, int] = {}
                try:
                    signals = await container.signal_store.list_signals()
                    signal_count = len(signals)
                    for s in signals:
                        sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
                        severity_breakdown[sev] = severity_breakdown.get(sev, 0) + 1
                except Exception:
                    pass
                display.show_perception(
                    tbox_injected=container.domain_ontology is not None,
                    signal_count=signal_count,
                    severity_breakdown=severity_breakdown,
                )

            try:
                answer = await container.chat_agent.run_chat_agent(
                    agent_name,
                    session_latest.thread,
                    on_event,
                    sandbox_session_id=sandbox_session_id,
                )
            except Exception as exc:
                typer.echo(f"Error: {exc}", err=True)
                continue

            if not quiet:
                from remi.observability.tracer import get_current_trace_id

                display.show_done(trace_id=get_current_trace_id())

            assistant_msg = Message(role="assistant", content=answer)
            await container.chat_session_store.append_message(session.id, assistant_msg)

            typer.echo(f"\nremi> {answer}\n")
    finally:
        await container.sandbox.destroy_session(sandbox_session_id)
