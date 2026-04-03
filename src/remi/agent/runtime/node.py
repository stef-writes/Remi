"""AgentNode — config-driven agent with think-act-observe loop.

Thin orchestrator: resolves config, delegates context assembly to
ContextBuilder, tool execution to ToolExecutor, iteration to the
agent loop, and output formatting to thread utilities.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog

from remi.agent.config import AgentConfig
from remi.agent.context.frame import WorldState
from remi.agent.context.intent import classify_intent
from remi.agent.context.rendering import (
    extract_signal_references,
    render_active_signals,
    render_domain_context,
)
from remi.agent.conversation.thread import (
    build_initial_thread,
    format_output,
    last_assistant_content,
    trim_thread,
)
from remi.agent.llm.types import LLMProvider, estimate_cost
from remi.agent.observe.types import SpanKind, Tracer, get_current_trace_id
from remi.agent.runtime.base import BaseModule, Message, ModuleOutput
from remi.agent.runtime.deps import OnEventCallback, RuntimeContext
from remi.agent.runtime.llm_bridge import OnEventCallback as _OnEvent  # noqa: F811,F401
from remi.agent.runtime.loop import run_agent_loop
from remi.agent.runtime.tool_executor import ToolExecutor, build_tool_set

logger = structlog.get_logger("remi.agent")


async def _noop_event(_type: str, _data: dict[str, Any]) -> None:
    pass


@asynccontextmanager
async def _noop_trace() -> AsyncIterator[None]:
    yield None


class AgentNode(BaseModule):
    """A fully config-driven agent node.

    The Python class contains no domain logic. The agent's identity — its
    prompt, model, tools, memory behaviour, and output format — is declared
    entirely in YAML config and parsed into an ``AgentConfig``.
    """

    kind = "agent"

    async def run(self, inputs: dict[str, Any], context: RuntimeContext) -> ModuleOutput:
        _t0 = time.monotonic()
        cfg = AgentConfig.from_dict(self.config)

        mode = context.params.mode or context.extras.get("mode", "agent")

        effective_provider = (
            context.params.provider_name
            or context.extras.get("provider_name")
            or cfg.provider_for_mode(mode)
            or context.deps.default_provider
            or context.extras.get("default_provider")
        )
        effective_model = (
            context.params.model_name
            or context.extras.get("model_name")
            or cfg.model_for_mode(mode)
            or context.deps.default_model
            or context.extras.get("default_model")
        )
        if not effective_provider:
            raise RuntimeError(
                "No LLM provider resolved. Set REMI_LLM_PROVIDER, configure "
                "llm.default_provider in base.yaml, or pass provider on the request."
            )
        if not effective_model:
            raise RuntimeError(
                "No LLM model resolved. Set REMI_LLM_MODEL, configure "
                "llm.default_model in base.yaml, or pass model on the request."
            )

        cfg = cfg.model_copy(
            update={
                "provider": effective_provider,
                "model": effective_model,
                "system_prompt": cfg.system_prompt_for_mode(mode),
                "max_iterations": cfg.max_iterations_for_mode(mode),
            }
        )

        provider = _resolve_provider(cfg.provider, context)
        routing_provider: LLMProvider | None = None
        if cfg.tool_routing_model:
            routing_name = cfg.tool_routing_provider or cfg.provider
            if routing_name and routing_name != cfg.provider:
                routing_provider = _resolve_provider(routing_name, context)
            else:
                routing_provider = provider
        tool_defs, tool_execute = build_tool_set(cfg, context, mode=mode)
        memory = context.deps.memory_store or context.extras.get("memory_store")
        _raw_emit = context.params.on_event or context.extras.get("on_event") or _noop_event
        emit: OnEventCallback = _raw_emit  # type: ignore[assignment]
        tracer: Tracer | None = context.deps.tracer or context.extras.get("tracer")

        domain = context.deps.domain_tbox or context.extras.get("domain_tbox")
        world = WorldState.from_tbox(domain)
        domain_priming = (
            render_domain_context(domain, compact=cfg.compact_tbox) if domain is not None else ""
        )

        thread = build_initial_thread(
            cfg,
            inputs,
            domain_priming=domain_priming,
            world=world,
        )

        injection_phases: set[str] = {"signals", "graph", "memory"}
        max_tool_rounds: int | None = None
        user_question = _extract_user_question(thread)
        intent_result = classify_intent(user_question, cfg.intents)
        intent_name: str | None = None
        if intent_result is not None:
            intent_name, intent_cfg = intent_result
            injection_phases = set(intent_cfg.context_injection) - {"domain"}

            if intent_name == "conversation":
                tool_defs, tool_execute = [], None
                max_tool_rounds = 0
            elif intent_cfg.max_tool_rounds is not None:
                max_tool_rounds = intent_cfg.max_tool_rounds

            if intent_cfg.max_iterations is not None:
                cfg = cfg.model_copy(update={"max_iterations": intent_cfg.max_iterations})

        log = logger.bind(
            run_id=context.run_id,
            agent=cfg.name or "unknown",
            mode=mode,
            provider=cfg.provider,
            model=cfg.model,
            intent=intent_name,
        )
        log.info(
            "agent_run_start",
            max_iterations=cfg.max_iterations,
            tool_count=len(tool_defs),
            intent=intent_name,
            injection_phases=sorted(injection_phases),
        )

        tool_executor = ToolExecutor(tool_defs, tool_execute, tracer, log)
        thread = trim_thread(thread, cfg.max_history_turns)

        mgr_id = context.extras.get("manager_id")
        mgr_name = context.extras.get("manager_name")
        if mgr_id and mgr_name:
            prop_names = context.extras.get("manager_property_names", [])
            unit_count = context.extras.get("manager_unit_count", 0)
            prop_count = context.extras.get("manager_property_count", len(prop_names))
            scope_parts = [
                f"## Manager Focus: {mgr_name}\n",
                f"The user has selected **{mgr_name}** (manager_id=`{mgr_id}`).",
                f"This manager oversees {prop_count} properties with {unit_count} total units.",
            ]
            if prop_names:
                scope_parts.append("Properties: " + ", ".join(prop_names[:20]))
            scope_parts.append(
                "\n**You MUST scope all tool calls to this manager.** "
                f'Always pass `manager_id="{mgr_id}"` to onto_signals, '
                "onto_search, onto_aggregate, semantic_search, and any "
                "remi_data function that accepts manager_id. "
                "Only discuss data relevant to this manager's portfolio "
                "unless the user explicitly asks about the broader portfolio."
            )
            _insert_after_static(thread, Message(role="system", content="\n".join(scope_parts)))

        trace_cm = (
            tracer.start_trace(
                f"agent_run/{cfg.name or 'unknown'}",
                kind=SpanKind.GRAPH,
                run_id=context.run_id,
                agent=cfg.name,
                mode=mode,
                provider=cfg.provider,
                model=cfg.model,
            )
            if tracer is not None
            else _noop_trace()
        )
        async with trace_cm:
            ctx_builder = context.deps.context_builder
            signal_store = context.deps.signal_store or context.extras.get("signal_store")

            needs_signals = "signals" in injection_phases
            needs_graph = "graph" in injection_phases
            needs_memory = "memory" in injection_phases

            if tracer is not None and world.loaded:
                async with tracer.span(
                    SpanKind.PERCEPTION,
                    "tbox_priming",
                    **{k: v for k, v in world.to_dict().items() if k != "tbox_loaded"},
                ):
                    pass

            async def _load_memory() -> str | None:
                if not (needs_memory and memory and cfg.memory.auto_load and cfg.memory.namespace):
                    return None
                keys = await memory.list_keys(cfg.memory.namespace)
                if not keys:
                    return None
                entries: list[str] = []
                for key in keys[:10]:
                    val = await memory.recall(cfg.memory.namespace, key)
                    if val is not None:
                        entries.append(f"- {key}: {val}")
                return "\n".join(entries) if entries else None

            if ctx_builder is not None and (needs_signals or needs_graph):
                frame, memory_text = await asyncio.gather(
                    ctx_builder.build(
                        question=user_question,
                        tracer=tracer,
                        phases=injection_phases,
                        world=world,
                    ),
                    _load_memory(),
                )
                ctx_builder.inject_into_thread(thread, frame)
            else:
                memory_text_coro = _load_memory()

                if needs_signals and signal_store is not None:
                    signal_summary = await render_active_signals(signal_store)
                    if signal_summary:
                        tbox_in_thread = any(
                            m.role == "system" and m.content and "Domain Context" in str(m.content)
                            for m in thread[1:]
                        )
                        insert_idx = 2 if tbox_in_thread else 1
                        thread.insert(insert_idx, Message(role="system", content=signal_summary))

                memory_text = await memory_text_coro

            if memory_text:
                _insert_after_static(
                    thread,
                    Message(role="system", content=f"Past context:\n{memory_text}"),
                )

            usage_ledger = context.deps.usage_ledger or context.extras.get("usage_ledger")

            thread, run_usage = await run_agent_loop(
                cfg=cfg,
                thread=thread,
                provider=provider,
                tool_executor=tool_executor,
                emit=emit,
                tracer=tracer,
                log=log,
                max_tool_rounds=max_tool_rounds,
                routing_provider=routing_provider,
                usage_ledger=usage_ledger,
            )

            final = format_output(thread, cfg)
            cost = estimate_cost(
                cfg.model or "",
                run_usage.prompt_tokens,
                run_usage.completion_tokens,
            )
            latency_ms = round((time.monotonic() - _t0) * 1000)

            done_payload: dict[str, Any] = {
                "response": last_assistant_content(thread) or "",
                "usage": run_usage.to_dict(),
                "model": cfg.model,
                "provider": cfg.provider,
                "latency_ms": latency_ms,
                "trace_id": get_current_trace_id(),
            }
            if intent_name:
                done_payload["intent"] = intent_name
            if cost is not None:
                done_payload["cost"] = round(cost, 6)
            await emit("done", done_payload)

            log.info(
                "agent_run_done",
                latency_ms=latency_ms,
                intent=intent_name,
                prompt_tokens=run_usage.prompt_tokens,
                completion_tokens=run_usage.completion_tokens,
                total_tokens=run_usage.total_tokens,
                cost=round(cost, 6) if cost is not None else None,
            )

            if tracer is not None:
                final_text = final if isinstance(final, str) else json.dumps(final, default=str)
                signal_names = extract_signal_references(final_text, domain)
                async with tracer.span(
                    SpanKind.REASONING,
                    "agent_output",
                    model=cfg.model,
                    provider=cfg.provider,
                    output_length=len(final_text),
                    signals_referenced=signal_names,
                    has_recommendation=any(
                        kw in final_text.lower()
                        for kw in ("recommend", "suggest", "should", "consider", "action")
                    ),
                ):
                    pass

            if memory and cfg.memory.auto_save and cfg.memory.namespace and thread:
                last = last_assistant_content(thread)
                if last is not None:
                    await memory.store(cfg.memory.namespace, context.run_id, last)

            run_metadata: dict[str, Any] = {
                "model": cfg.model,
                "provider": cfg.provider,
                "trace_id": get_current_trace_id(),
                "usage": run_usage.to_dict(),
            }
            if cost is not None:
                run_metadata["cost"] = round(cost, 6)

            return ModuleOutput(
                value=final,
                contract=cfg.output_contract,
                metadata=run_metadata,
            )


def _insert_after_static(thread: list[Message], msg: Message) -> None:
    """Insert *msg* after static system messages but before the user message.

    Anthropic caches from the beginning of the context window.  Keeping
    the static prefix (system prompt + TBox priming) contiguous maximises
    cache-read hits.  Dynamic per-turn content goes between the static
    prefix and the first non-system message.
    """
    idx = 0
    for i, m in enumerate(thread):
        if m.role == "system":
            idx = i + 1
        else:
            break
    thread.insert(idx, msg)


def _extract_user_question(thread: list[Message]) -> str | None:
    """Return the content of the last user message in the thread."""
    for msg in reversed(thread):
        if msg.role == "user" and msg.content:
            return str(msg.content)
    return None


def _resolve_provider(provider_name: str | None, context: RuntimeContext) -> LLMProvider:
    """Resolve the LLM provider via the factory."""
    factory = context.deps.provider_factory or context.extras.get("provider_factory")
    if factory is not None:
        return factory.create(provider_name or "")

    raise RuntimeError(
        f"No LLM provider factory in context. Cannot resolve provider '{provider_name}'. "
        "Ensure the container wires a LLMProviderFactory into context deps or extras."
    )
