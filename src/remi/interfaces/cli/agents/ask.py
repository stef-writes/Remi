"""remi ask — single-shot AI questions to the director agent."""

from __future__ import annotations

import asyncio

import typer

from remi.interfaces.cli.shared import get_container, json_out, use_json

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
    from remi.infrastructure.loaders.yaml_loader import YamlAppLoader
    from remi.interfaces.cli.live_display import LiveAgentDisplay
    from remi.shared.ids import AppId, ModuleId
    from remi.shared.paths import WORKFLOWS_DIR

    container = get_container()
    app_name = "director"
    app_path = WORKFLOWS_DIR / app_name / "app.yaml"

    if not app_path.exists():
        json_out({"ok": False, "error": f"App not found: {app_path}"})
        raise typer.Exit(1)

    loader = YamlAppLoader()
    try:
        app_def = loader.load(str(app_path))
    except Exception as exc:
        json_out({"ok": False, "error": str(exc)})
        raise typer.Exit(1) from None

    reg_result = container.register_app_uc.execute(app_def)
    if reg_result.is_err:
        json_out({"ok": False, "errors": reg_result.unwrap_err()})
        raise typer.Exit(1)

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

        agent_module = next((m for m in app_def.modules if m.kind == "agent"), None)
        model = agent_module.config.get("model", "?") if agent_module else "?"
        provider = agent_module.config.get("provider", "?") if agent_module else "?"
        display.show_start(app_name, model, provider)
        display.show_perception(
            tbox_injected=container.domain_ontology is not None,
            signal_count=signal_count,
            severity_breakdown=severity_breakdown,
        )

    result = await container.run_app_uc.execute(
        AppId(app_def.app_id),
        run_params={"input": question},
    )

    agent_module_ids = [m.id for m in app_def.modules if m.kind == "agent"]
    output_mid = agent_module_ids[-1] if agent_module_ids else app_def.modules[-1].id

    state = await container.state_query.get_module_state(
        AppId(app_def.app_id), result.run_id, ModuleId(output_mid)
    )

    answer = state.output if state else None

    if fmt_json:
        json_out({
            "ok": result.status.value == "completed",
            "agent": app_name,
            "run_id": result.run_id,
            "question": question,
            "answer": answer,
        })
    else:
        if display:
            from remi.infrastructure.trace.tracer import get_current_trace_id
            display.show_done(trace_id=get_current_trace_id())
        if answer:
            typer.echo(f"\n{answer}\n")
        else:
            typer.echo("No response generated.", err=True)
            if result.errors:
                for err in result.errors:
                    typer.echo(f"  Error: {err}", err=True)
            raise typer.Exit(1)
