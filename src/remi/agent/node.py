"""AgentNode — config-driven agent with think-act-observe loop.

Thin orchestrator: resolves config, delegates context assembly to
ContextBuilder, tool execution to ToolExecutor, iteration to the
agent loop, and output formatting to thread utilities.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import structlog

from remi.agent.base import BaseModule, Message, ModuleOutput
from remi.agent.config import AgentConfig
from remi.agent.context import RuntimeContext
from remi.agent.llm_bridge import OnEventCallback
from remi.agent.loop import run_agent_loop
from remi.agent.thread import build_initial_thread, format_output, last_assistant_content
from remi.agent.tool_executor import ToolExecutor, build_tool_set
from remi.knowledge.context_builder import extract_signal_references
from remi.llm.ports import LLMProvider
from remi.llm.pricing import estimate_cost
from remi.models.trace import SpanKind
from remi.observability.tracer import Tracer, get_current_trace_id

logger = structlog.get_logger("remi.agent")


async def _noop_event(_type: str, _data: dict[str, Any]) -> None:
    pass


@asynccontextmanager
async def _noop_trace():
    yield None


class AgentNode(BaseModule):
    """A fully config-driven agent node.

    The Python class contains no domain logic. The agent's identity — its
    prompt, model, tools, memory behaviour, and output format — is declared
    entirely in YAML config and parsed into an ``AgentConfig``.
    """

    kind = "agent"

    async def run(self, inputs: dict[str, Any], context: RuntimeContext) -> ModuleOutput:
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
        tool_defs, tool_execute = build_tool_set(cfg, context, mode=mode)
        memory = context.deps.memory_store or context.extras.get("memory_store")
        emit: OnEventCallback = (
            context.params.on_event or context.extras.get("on_event") or _noop_event
        )
        tracer: Tracer | None = context.deps.tracer or context.extras.get("tracer")

        log = logger.bind(
            run_id=context.run_id,
            agent=cfg.name or "unknown",
            mode=mode,
            provider=cfg.provider,
            model=cfg.model,
        )
        log.info(
            "agent_run_start",
            max_iterations=cfg.max_iterations,
            tool_count=len(tool_defs),
        )

        tool_executor = ToolExecutor(tool_defs, tool_execute, tracer, log)
        thread = build_initial_thread(cfg, inputs)

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
            domain = context.deps.domain_ontology or context.extras.get("domain_ontology")
            ctx_builder = context.deps.context_builder
            signal_store = context.deps.signal_store or context.extras.get("signal_store")

            if ctx_builder is not None:
                frame = await ctx_builder.build(tracer=tracer)
                ctx_builder.inject_into_thread(thread, frame)
            else:
                if domain is not None:
                    from remi.knowledge.context_builder import render_domain_context

                    ctx_block = render_domain_context(domain)
                    if ctx_block:
                        thread.insert(1, Message(role="system", content=ctx_block))
                        if tracer is not None:
                            async with tracer.span(
                                SpanKind.PERCEPTION,
                                "tbox_injection",
                                signal_definitions=len(getattr(domain, "signals", {})),
                                threshold_count=len(getattr(domain, "thresholds", {})),
                                policy_count=len(getattr(domain, "policies", [])),
                                causal_chain_count=len(getattr(domain, "causal_chains", [])),
                            ):
                                pass

                if signal_store is not None:
                    from remi.knowledge.context_builder import render_active_signals

                    signal_summary = await render_active_signals(signal_store)
                    if signal_summary:
                        tbox_in_thread = any(
                            m.role == "system" and m.content and "Domain Context" in str(m.content)
                            for m in thread[1:]
                        )
                        insert_idx = 2 if tbox_in_thread else 1
                        thread.insert(insert_idx, Message(role="system", content=signal_summary))
                        if tracer is not None:
                            try:
                                all_sigs = await signal_store.list_signals()
                                severity_counts: dict[str, int] = {}
                                for s in all_sigs:
                                    sev = (
                                        s.severity.value
                                        if hasattr(s.severity, "value")
                                        else str(s.severity)
                                    )
                                    severity_counts[sev] = severity_counts.get(sev, 0) + 1
                                async with tracer.span(
                                    SpanKind.PERCEPTION,
                                    "signal_injection",
                                    active_signals=len(all_sigs),
                                    severity_breakdown=severity_counts,
                                    signal_types=[s.signal_type for s in all_sigs][:25],
                                ):
                                    pass
                            except Exception:
                                pass

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

            thread, run_usage = await run_agent_loop(
                cfg=cfg,
                thread=thread,
                provider=provider,
                tool_executor=tool_executor,
                emit=emit,
                tracer=tracer,
                log=log,
            )

            final = format_output(thread, cfg)
            cost = estimate_cost(
                cfg.model or "",
                run_usage.prompt_tokens,
                run_usage.completion_tokens,
            )
            done_payload: dict[str, Any] = {
                "response": final if isinstance(final, str) else json.dumps(final, default=str),
                "usage": run_usage.to_dict(),
                "model": cfg.model,
                "provider": cfg.provider,
            }
            if cost is not None:
                done_payload["cost"] = round(cost, 6)
            await emit("done", done_payload)

            log.info(
                "agent_run_done",
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


def _resolve_provider(provider_name: str, context: RuntimeContext) -> LLMProvider:
    """Resolve the LLM provider via the factory."""
    factory = context.deps.provider_factory or context.extras.get("provider_factory")
    if factory is not None:
        return factory.create(provider_name)

    raise RuntimeError(
        f"No LLM provider factory in context. Cannot resolve provider '{provider_name}'. "
        "Ensure the container wires a LLMProviderFactory into context deps or extras."
    )
