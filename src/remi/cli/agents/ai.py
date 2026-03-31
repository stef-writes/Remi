"""remi ai — unified CLI for REMI agent interactions.

Supports single-shot questions (default) and interactive multi-turn chat
via --interactive. Mode selects the agent behaviour: "ask" for fast Q&A
with structured data tools, "agent" for autonomous analysis with sandbox.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from remi.cli.shared import get_container_async, json_out, use_json

cmd = typer.Typer(name="ai", help="Interact with REMI AI agents.", no_args_is_help=True)


@cmd.callback(invoke_without_command=True)
def ai(
    question: str = typer.Argument(None, help="Natural language question (omit for interactive)"),
    agent: str = typer.Option("director", "--agent", "-a", help="Agent to use"),
    mode: str = typer.Option("ask", "--mode", "-m", help="Mode: ask (fast Q&A) or agent (deep analysis)"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Start interactive chat session"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show LLM output live"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output (interactive only)"),
) -> None:
    """Ask REMI a question or start an interactive chat session."""
    if mode not in ("ask", "agent"):
        typer.echo(f"Invalid mode: {mode}. Use 'ask' or 'agent'.", err=True)
        raise typer.Exit(1)

    if interactive or question is None:
        if question is not None:
            typer.echo("Ignoring positional question in interactive mode.", err=True)
        asyncio.run(_run_interactive(agent, mode, verbose=verbose, quiet=quiet))
    else:
        asyncio.run(_run_single(agent, question, mode, use_json(json_output), verbose))


async def _run_single(
    agent_name: str,
    question: str,
    mode: str,
    fmt_json: bool,
    verbose: bool,
) -> None:
    from remi.cli.live_display import LiveAgentDisplay

    container = await get_container_async()

    display: LiveAgentDisplay | None = None
    if not fmt_json:
        display = LiveAgentDisplay(verbose=verbose)

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

        settings = container.settings
        display.show_start(
            agent_name,
            settings.llm.default_model,
            settings.llm.default_provider,
        )
        display.show_perception(
            tbox_injected=container.domain_rulebook is not None,
            signal_count=signal_count,
            severity_breakdown=severity_breakdown,
        )

    try:
        answer, run_id = await container.chat_agent.ask(
            agent_name, question, mode=mode,  # type: ignore[arg-type]
        )
    except Exception as exc:
        if fmt_json:
            json_out({"ok": False, "error": str(exc)})
        else:
            typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from None

    if fmt_json:
        json_out(
            {
                "ok": True,
                "agent": agent_name,
                "run_id": run_id,
                "mode": mode,
                "question": question,
                "answer": answer,
            }
        )
    else:
        if display:
            from remi.observability.tracer import get_current_trace_id

            display.show_done(trace_id=get_current_trace_id())
        if answer:
            typer.echo(f"\n{answer}\n")
        else:
            typer.echo("No response generated.", err=True)
            raise typer.Exit(1)


async def _run_interactive(
    agent_name: str,
    mode: str,
    verbose: bool = False,
    quiet: bool = False,
) -> None:
    from remi.cli.live_display import LiveAgentDisplay
    from remi.models.chat import Message

    container = await get_container_async()
    session = await container.chat_session_store.create(agent_name)

    sandbox_session_id = f"chat-{session.id}"
    await container.sandbox.create_session(sandbox_session_id)

    mode_label = "ask (fast)" if mode == "ask" else "agent (deep)"
    typer.echo(f"REMI — agent: {agent_name} | mode: {mode_label} | session: {session.id}")
    typer.echo("Type your question and press Enter. Use /quit to exit, /mode to toggle.\n")

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
            if user_input.lower() in ("/mode", "/toggle"):
                mode = "agent" if mode == "ask" else "ask"
                mode_label = "ask (fast)" if mode == "ask" else "agent (deep)"
                typer.echo(f"  Switched to {mode_label} mode.\n")
                continue

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
                    tbox_injected=container.domain_rulebook is not None,
                    signal_count=signal_count,
                    severity_breakdown=severity_breakdown,
                )

            try:
                answer = await container.chat_agent.run_chat_agent(
                    agent_name,
                    session_latest.thread,
                    on_event,
                    sandbox_session_id=sandbox_session_id,
                    mode=mode,  # type: ignore[arg-type]
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
