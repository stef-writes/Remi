"""AgentNode — config-driven agent with think-act-observe loop.

Model-agnostic: the node resolves its LLM provider at runtime via the
``LLMProviderFactory`` in context extras. Messages and tool definitions
are passed as REMI-neutral types; each provider handles wire-format
translation internally.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from remi.domain.modules.base import BaseModule, Message, ModuleOutput
from remi.domain.modules.builtins.agent_config import AgentConfig
from remi.domain.trace.types import SpanKind

if TYPE_CHECKING:
    from remi.domain.tools.ports import ToolDefinition
    from remi.infrastructure.llm.ports import LLMProvider
    from remi.infrastructure.trace.tracer import Tracer
    from remi.runtime.context.runtime_context import RuntimeContext

OnEventCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


async def _noop_event(_type: str, _data: dict[str, Any]) -> None:
    pass


class AgentNode(BaseModule):
    """A fully config-driven agent node.

    The Python class contains no domain logic. The agent's identity — its
    prompt, model, tools, memory behaviour, and output format — is declared
    entirely in YAML config and parsed into an ``AgentConfig``.

    If ``context.extras["on_event"]`` is set to an async callback, the agent
    emits streaming events during execution: ``delta``, ``tool_call``,
    ``tool_result``, ``done``, and ``error``.
    """

    kind = "agent"

    async def run(self, inputs: dict[str, Any], context: RuntimeContext) -> ModuleOutput:
        cfg = AgentConfig.from_dict(self.config)
        provider = _resolve_provider(cfg.provider, context)
        tool_defs, tool_execute = _build_tool_set(cfg, context)
        memory = _resolve_memory(context)
        emit: OnEventCallback = context.extras.get("on_event") or _noop_event
        tracer: Tracer | None = context.extras.get("tracer")

        thread = _build_initial_thread(cfg, inputs)

        # --- Perception: inject TBox world model ---
        domain = context.extras.get("domain_ontology")
        tbox_injected = False
        if domain is not None:
            ctx_block = _render_domain_context(domain)
            if ctx_block:
                thread.insert(1, Message(role="system", content=ctx_block))
                tbox_injected = True
                if tracer is not None:
                    async with tracer.span(
                        SpanKind.PERCEPTION, "tbox_injection",
                        signal_definitions=len(getattr(domain, "signals", {})),
                        threshold_count=len(getattr(domain, "thresholds", {})),
                        policy_count=len(getattr(domain, "policies", [])),
                        causal_chain_count=len(getattr(domain, "causal_chains", [])),
                    ):
                        pass

        # --- Perception: inject active signals ---
        signal_store = context.extras.get("signal_store")
        active_signal_count = 0
        if signal_store is not None:
            signal_summary = await _render_active_signals(signal_store)
            if signal_summary:
                insert_idx = 2 if tbox_injected else 1
                thread.insert(insert_idx, Message(role="system", content=signal_summary))
                try:
                    all_signals = await signal_store.list_signals()
                    active_signal_count = len(all_signals)
                except Exception:
                    pass
                if tracer is not None:
                    severity_counts: dict[str, int] = {}
                    for s in (all_signals if active_signal_count else []):
                        sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
                        severity_counts[sev] = severity_counts.get(sev, 0) + 1
                    async with tracer.span(
                        SpanKind.PERCEPTION, "signal_injection",
                        active_signals=active_signal_count,
                        severity_breakdown=severity_counts,
                        signal_types=[s.signal_type for s in (all_signals if active_signal_count else [])][:25],
                    ):
                        pass

        # --- Memory loading ---
        if memory and cfg.memory.auto_load and cfg.memory.namespace:
            keys = await memory.list_keys(cfg.memory.namespace)
            if keys:
                entries = []
                for key in keys[:10]:
                    val = await memory.recall(cfg.memory.namespace, key)
                    if val is not None:
                        entries.append(f"- {key}: {val}")
                if entries:
                    past = "\n".join(entries)
                    thread.insert(1, Message(role="system", content=f"Past context:\n{past}"))

        # --- Think-act-observe loop ---
        total_iterations = 0
        for iteration in range(cfg.max_iterations):
            total_iterations = iteration + 1
            llm_kwargs: dict[str, Any] = {
                "model": cfg.model,
                "messages": thread,
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
            }
            if tool_defs:
                llm_kwargs["tools"] = tool_defs

            # --- LLM call ---
            if tracer is not None:
                async with tracer.span(
                    SpanKind.LLM_CALL, f"{cfg.provider}/{cfg.model}",
                    provider=cfg.provider,
                    model=cfg.model,
                    iteration=iteration,
                    message_count=len(thread),
                    temperature=cfg.temperature,
                    has_tools=bool(tool_defs),
                ) as llm_ctx:
                    response = await provider.complete(**llm_kwargs)
                    llm_ctx.set_attribute("has_tool_calls", bool(response.tool_calls))
                    llm_ctx.set_attribute("response_length", len(response.content or ""))
                    if hasattr(response, "usage") and response.usage:
                        llm_ctx.set_attribute("usage", response.usage)
            else:
                response = await provider.complete(**llm_kwargs)

            if not response.tool_calls:
                content = response.content or ""
                if cfg.response_format == "json":
                    content = _try_parse_json(content)
                thread.append(Message(role="assistant", content=content))
                await emit("delta", {"content": content, "iteration": iteration})
                break

            if response.content:
                await emit("delta", {"content": response.content, "iteration": iteration})

            thread.append(Message(role="assistant", content=response.content or ""))
            for tc in response.tool_calls:
                await emit("tool_call", {
                    "tool": tc.name, "arguments": tc.arguments, "call_id": tc.id,
                })

                # --- Tool call ---
                if tracer is not None:
                    async with tracer.span(
                        SpanKind.TOOL_CALL, tc.name,
                        tool_name=tc.name,
                        arguments=tc.arguments,
                        call_id=tc.id,
                        iteration=iteration,
                    ) as tool_ctx:
                        if tool_execute is not None:
                            result = await tool_execute(tc.name, tc.arguments)
                        else:
                            result = {"error": f"Tool {tc.name} not available"}
                        tool_ctx.set_attribute(
                            "result_preview",
                            _truncate(result, 500),
                        )
                else:
                    if tool_execute is not None:
                        result = await tool_execute(tc.name, tc.arguments)
                    else:
                        result = {"error": f"Tool {tc.name} not available"}

                thread.append(
                    Message(role="tool", name=tc.name, tool_call_id=tc.id, content=result)
                )
                await emit("tool_result", {
                    "tool": tc.name, "call_id": tc.id,
                    "result": result if isinstance(result, (str, int, float, bool)) else json.dumps(result, default=str),
                })

        final = _format_output(thread, cfg)
        await emit("done", {"response": final if isinstance(final, str) else json.dumps(final, default=str)})

        # --- Reasoning trace: capture what the agent concluded ---
        if tracer is not None:
            final_text = final if isinstance(final, str) else json.dumps(final, default=str)
            signal_names = _extract_signal_references(final_text, domain)
            async with tracer.span(
                SpanKind.REASONING, "agent_output",
                model=cfg.model,
                provider=cfg.provider,
                iterations=total_iterations,
                output_length=len(final_text),
                signals_referenced=signal_names,
                has_recommendation=any(
                    kw in final_text.lower()
                    for kw in ("recommend", "suggest", "should", "consider", "action")
                ),
            ):
                pass

        if memory and cfg.memory.auto_save and cfg.memory.namespace and thread:
            last_assistant = _last_assistant_content(thread)
            if last_assistant is not None:
                await memory.store(cfg.memory.namespace, context.run_id, last_assistant)

        return ModuleOutput(
            value=final,
            contract=cfg.output_contract,
            metadata={
                "model": cfg.model,
                "provider": cfg.provider,
                "iterations": total_iterations,
                "trace_id": _get_trace_id(),
            },
        )


def _resolve_provider(provider_name: str, context: RuntimeContext) -> LLMProvider:
    """Resolve the LLM provider via the factory (model-agnostic)."""
    factory = context.extras.get("provider_factory")
    if factory is not None:
        return factory.create(provider_name)

    raise RuntimeError(
        f"No LLM provider factory in context. Cannot resolve provider '{provider_name}'. "
        "Ensure the container wires a LLMProviderFactory into context_extras['provider_factory']."
    )


def _build_tool_set(
    cfg: AgentConfig, context: RuntimeContext
) -> tuple[list[ToolDefinition], Any]:
    """Build tool definitions and an executor scoped to declared tools.

    Returns (tool_definitions, execute_fn) where execute_fn is
    ``async (name, args) -> result`` or None if no tools.
    """
    registry = context.extras.get("tool_registry")
    if not registry or not cfg.tools:
        return [], None

    tool_names = [t.name for t in cfg.tools]
    definitions = registry.list_definitions(names=tool_names)

    tool_configs = {t.name: t.config for t in cfg.tools}

    async def execute(name: str, arguments: dict[str, Any]) -> Any:
        entry = registry.get(name)
        if entry is None:
            return {"error": f"Tool '{name}' not found"}
        fn, _ = entry
        merged = {**tool_configs.get(name, {}), **arguments}
        return await fn(merged)

    return definitions, execute


def _resolve_memory(context: RuntimeContext) -> Any:
    return context.extras.get("memory_store")


def _build_initial_thread(
    cfg: AgentConfig, inputs: dict[str, Any]
) -> list[Message]:
    thread: list[Message] = []

    thread.append(Message(role="system", content=cfg.system_prompt))

    upstream_thread = inputs.get("thread")
    if isinstance(upstream_thread, list) and upstream_thread:
        for item in upstream_thread:
            if isinstance(item, Message):
                thread.append(item)
            elif isinstance(item, dict):
                thread.append(Message(**item))
    elif cfg.input_template:
        flat = _flatten_inputs(inputs)
        try:
            rendered = cfg.input_template.format(**flat)
        except KeyError:
            rendered = cfg.input_template.format(input=json.dumps(flat, default=str))
        thread.append(Message(role="user", content=rendered))
    else:
        content = _summarize_inputs(inputs)
        thread.append(Message(role="user", content=content))

    return thread


def _flatten_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, val in inputs.items():
        safe_key = key.replace("-", "_")
        if isinstance(val, dict):
            flat.update(val)
        flat[safe_key] = val
        flat[key] = val if not isinstance(val, (dict, list)) else json.dumps(val, default=str)
    if len(inputs) == 1:
        flat["input"] = next(iter(inputs.values()))
    return flat


def _summarize_inputs(inputs: dict[str, Any]) -> str:
    parts = []
    for key, val in inputs.items():
        if isinstance(val, (dict, list)):
            parts.append(f"{key}: {json.dumps(val, default=str)}")
        else:
            parts.append(f"{key}: {val}")
    return "\n".join(parts)


def _format_output(thread: list[Message], cfg: AgentConfig) -> Any:
    if cfg.output_contract == "conversation":
        return [msg.model_dump() for msg in thread]
    last = _last_assistant_content(thread)
    return last


def _last_assistant_content(thread: list[Message]) -> Any:
    for msg in reversed(thread):
        if msg.role == "assistant":
            return msg.content
    return None


def _try_parse_json(text: str | Any) -> Any:
    if not isinstance(text, str):
        return text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def _render_domain_context(domain: Any) -> str:
    """Render the TBox into a compact system message block.

    Reads typed DomainOntology models — SignalDefinitions, Policies,
    CausalChains — and produces a structured context for the LLM.
    """
    from remi.domain.signals.types import DomainOntology

    parts = ["## Domain Context (from ontology)\n"]

    if not isinstance(domain, DomainOntology):
        return ""

    if domain.signals:
        signal_lines = []
        for defn in domain.signals.values():
            desc = defn.description.split("\n")[0].strip()
            signal_lines.append(
                f"- **{defn.name}** [{defn.severity.value}] ({defn.entity}): {desc}"
            )
        parts.append("**Signal definitions (what the entailment engine detects):**")
        parts.append("\n".join(signal_lines))

    if domain.thresholds:
        threshold_lines = [f"- {key}: {val}" for key, val in domain.thresholds.items()]
        parts.append("\n**Operational thresholds:**")
        parts.append("\n".join(threshold_lines))

    if domain.policies:
        policy_lines = [
            f"- [{pol.deontic.value}] {pol.description}" for pol in domain.policies
        ]
        parts.append("\n**Deontic obligations:**")
        parts.append("\n".join(policy_lines))

    if domain.causal_chains:
        chain_lines = [
            f"- {c.cause} → {c.effect}: {c.description}" for c in domain.causal_chains
        ]
        parts.append("\n**Known causal relationships:**")
        parts.append("\n".join(chain_lines))

    parts.append(
        "\nWhen you detect data matching any signal definition above, "
        "name it explicitly by its domain signal name. Use causal chains "
        "to connect related signals. Reference policies when recommending actions."
    )
    return "\n".join(parts)


def _get_trace_id() -> str | None:
    from remi.infrastructure.trace.tracer import get_current_trace_id
    return get_current_trace_id()


def _truncate(value: Any, max_len: int = 500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:max_len] + ("..." if len(text) > max_len else "")


def _extract_signal_references(text: str, domain: Any) -> list[str]:
    """Find signal names mentioned in the agent's output."""
    if domain is None or not hasattr(domain, "all_signal_names"):
        return []
    found = []
    for name in domain.all_signal_names():
        if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
            found.append(name)
    return found


async def _render_active_signals(signal_store: Any) -> str:
    """Fetch current signals and render a compact summary for the LLM."""
    try:
        signals = await signal_store.list_signals()
    except Exception:
        return ""

    if not signals:
        return (
            "## Active Signals (0)\n\n"
            "No signals currently active. The portfolio appears within normal parameters. "
            "If the user asks about problems, verify by querying the data directly."
        )

    severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}

    lines = [f"## Active Signals ({len(signals)})\n"]
    for s in signals[:25]:
        sev_val = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
        icon = severity_icon.get(sev_val, "❓")
        lines.append(
            f"- {icon} **[{sev_val.upper()}] {s.signal_type}**: "
            f"{s.entity_name} — {s.description}  \n"
            f"  `{s.signal_id}` (use onto_explain for evidence)"
        )

    lines.append(
        "\nThese signals are pre-computed from the data. Reference them by name "
        "in your response. Use `onto_explain` with the signal_id for the full "
        "evidence chain."
    )
    return "\n".join(lines)
