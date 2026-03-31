"""remi ask — single-shot AI questions to the director agent."""

from __future__ import annotations

import asyncio

import typer

from remi.cli.shared import get_container_async, json_out, use_json

cmd = typer.Typer(name="ask", help="Ask REMI an AI-powered question.", no_args_is_help=True)


@cmd.callback(invoke_without_command=True)
def ask(
    question: str = typer.Argument(..., help="Natural language question"),
    json_output: bool = typer.Option(False, "--json", "-j"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show LLM output live"),
) -> None:
    """Ask the REMI director agent a question."""
    asyncio.run(_run_ask(question, use_json(json_output), verbose))


async def _run_ask(question: str, fmt_json: bool, verbose: bool = False) -> None:
    from remi.cli.live_display import LiveAgentDisplay

    container = await get_container_async()
    agent_name = "director"

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
            tbox_injected=container.domain_ontology is not None,
            signal_count=signal_count,
            severity_breakdown=severity_breakdown,
        )

    try:
        answer, run_id = await container.chat_agent.ask(agent_name, question)
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
