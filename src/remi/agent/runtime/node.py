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
from remi.agent.context.builder import _find_tail_inject_point
from remi.agent.context.frame import WorldState
from remi.agent.context.rendering import render_domain_context
from remi.agent.llm.types import LLMProvider, estimate_cost
from remi.agent.memory import MemoryStore
from remi.agent.memory.extraction import extract_episode
from remi.agent.observe.types import SpanKind, Tracer, get_current_trace_id
from remi.agent.runtime.base import BaseModule, Message, ModuleOutput
from remi.agent.runtime.conversation.thread import (
    build_initial_thread,
    format_output,
    trim_thread,
)
from remi.agent.runtime.deps import OnEventCallback, RuntimeContext, ScopeContext
from remi.agent.runtime.loop import run_agent_loop
from remi.agent.runtime.tool_executor import ToolExecutor, resolve_agent_tools
from remi.agent.skills import FilesystemSkillDiscovery, SkillMetadata
from remi.agent.workspace import inject_workspace, load_workspace
from remi.agent.workspace.flush import flush_before_trim

logger = structlog.get_logger("remi.agent")


async def _noop_event(_type: str, _data: dict[str, Any]) -> None:
    pass


def _render_skills_catalog(skills: list[SkillMetadata]) -> str:
    """Render discovered skills as a system message for the agent."""
    if not skills:
        return ""
    lines = ["## Available Skills", ""]
    for s in skills:
        tags = f" [{', '.join(s.tags)}]" if s.tags else ""
        lines.append(f"- **{s.name}**{tags}: {s.description}")
    lines.append("")
    lines.append(
        "When a task matches a skill, follow the skill's commands and "
        "workflows using the `remi` CLI via the `bash` tool."
    )
    return "\n".join(lines)


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
            or cfg.provider
            or context.deps.default_provider
            or context.extras.get("default_provider")
        )
        effective_model = (
            context.params.model_name
            or context.extras.get("model_name")
            or cfg.model
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
        compaction_provider: LLMProvider | None = None
        if cfg.compaction_model and cfg.provider:
            compaction_provider = _resolve_provider(cfg.provider, context)
        bindings = resolve_agent_tools(cfg, context, mode=mode)
        memory = context.deps.memory_store or context.extras.get("memory_store")
        _raw_emit = context.params.on_event or context.extras.get("on_event") or _noop_event
        emit: OnEventCallback = _raw_emit  # type: ignore[assignment]
        tracer: Tracer | None = context.deps.tracer or context.extras.get("tracer")

        domain = context.deps.domain_tbox or context.extras.get("domain_tbox")
        world = WorldState.from_schema(domain)
        domain_priming = render_domain_context(domain) if domain is not None else ""

        thread = build_initial_thread(
            cfg,
            inputs,
            domain_priming=domain_priming,
            world=world,
        )

        max_tool_rounds: int | None = None
        token_budget: int | None = None
        try:
            from remi.agent.workflow.loader import load_manifest_runtime

            runtime_cfg = load_manifest_runtime(cfg.name)
            if runtime_cfg.resources.max_tool_rounds is not None:
                max_tool_rounds = runtime_cfg.resources.max_tool_rounds
            if runtime_cfg.resources.max_tokens is not None:
                token_budget = runtime_cfg.resources.max_tokens
        except (ValueError, FileNotFoundError):
            pass

        user_question = _extract_user_question(thread)

        # Skip expensive graph/memory injection when the agent has no tools
        # (pure conversation) or the message is trivially short.
        needs_enrichment = bool(bindings) and _needs_context(user_question)
        injection_phases: set[str] = {"graph", "memory"} if needs_enrichment else set()

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
            tool_count=len(bindings),
            injection_phases=sorted(injection_phases),
        )

        tool_executor = ToolExecutor.from_bindings(bindings, tracer, log)

        sandbox_for_flush = context.extras.get("sandbox")
        flush_sid = context.params.sandbox_session_id
        if sandbox_for_flush is not None and flush_sid:
            await flush_before_trim(thread, cfg.max_history_turns, sandbox_for_flush, flush_sid)

        thread = trim_thread(thread, cfg.max_history_turns)

        scope: ScopeContext = context.scope
        if scope.scope_message:
            _insert_before_last_user(thread, Message(role="system", content=scope.scope_message))

        sandbox_sid = context.params.sandbox_session_id
        sandbox = context.extras.get("sandbox")
        if sandbox is not None and sandbox_sid:
            workspace = await load_workspace(sandbox, sandbox_sid)
            inject_workspace(thread, workspace)

        if cfg.skills_paths:
            discovery = FilesystemSkillDiscovery(cfg.skills_paths)
            discovered = discovery.discover()
            skills_text = _render_skills_catalog(discovered)
            if skills_text:
                _insert_before_last_user(thread, Message(role="system", content=skills_text))
            context = context.with_extras(skill_discovery=discovery)

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

            needs_graph = "graph" in injection_phases
            needs_memory = "memory" in injection_phases

            if tracer is not None and world.loaded:
                async with tracer.span(
                    SpanKind.PERCEPTION,
                    "schema_priming",
                    **{k: v for k, v in world.to_dict().items() if k != "schema_loaded"},
                ):
                    pass

            recall_service = context.deps.recall_service
            scope_entity_ids = [context.scope.entity_id] if context.scope.entity_id else None

            async def _recall_memory() -> str | None:
                if not (needs_memory and recall_service and cfg.memory.auto_load):
                    return None
                entries = await recall_service.recall(
                    user_question,
                    entity_ids=scope_entity_ids,
                )
                return recall_service.render(entries)

            if ctx_builder is not None and needs_graph:
                frame, memory_text = await asyncio.gather(
                    ctx_builder.build(
                        question=user_question,
                        tracer=tracer,
                        phases=injection_phases,
                        world=world,
                    ),
                    _recall_memory(),
                )
                ctx_builder.inject_into_thread(thread, frame)
            else:
                memory_text = await _recall_memory()

            if memory_text:
                _insert_before_last_user(
                    thread,
                    Message(role="system", content=memory_text),
                )

            usage_ledger = context.deps.usage_ledger or context.extras.get("usage_ledger")

            try:
                caps = provider.model_capabilities(cfg.model or "")
                context_budget = caps.context_window
            except Exception:
                context_budget = 0

            infer_result_schema = context.extras.get("infer_result_schema")

            thread, run_usage = await run_agent_loop(
                cfg=cfg,
                thread=thread,
                provider=provider,
                tool_executor=tool_executor,
                emit=emit,
                tracer=tracer,
                log=log,
                max_tool_rounds=max_tool_rounds,
                max_tokens=token_budget,
                routing_provider=routing_provider,
                compaction_provider=compaction_provider,
                usage_ledger=usage_ledger,
                memory=memory,
                memory_namespace=cfg.memory.namespace,
                context_budget=context_budget,
                infer_result_schema=infer_result_schema,
            )

            final = format_output(thread, cfg)
            cost = estimate_cost(
                cfg.model or "",
                run_usage.prompt_tokens,
                run_usage.completion_tokens,
            )
            latency_ms = round((time.monotonic() - _t0) * 1000)
            cache_ratio = (
                run_usage.cache_read_tokens / run_usage.prompt_tokens
                if run_usage.prompt_tokens > 0
                else 0.0
            )

            done_payload: dict[str, Any] = {
                "usage": run_usage.to_dict(),
                "model": cfg.model,
                "provider": cfg.provider,
                "latency_ms": latency_ms,
                "trace_id": get_current_trace_id(),
                "cache_hit_ratio": round(cache_ratio, 3),
            }
            if cost is not None:
                done_payload["cost"] = round(cost, 6)
            await emit("done", done_payload)

            log.info(
                "agent_run_done",
                latency_ms=latency_ms,
                prompt_tokens=run_usage.prompt_tokens,
                completion_tokens=run_usage.completion_tokens,
                total_tokens=run_usage.total_tokens,
                cache_read_tokens=run_usage.cache_read_tokens,
                cache_creation_tokens=run_usage.cache_creation_tokens,
                cache_hit_ratio=round(cache_ratio, 3),
                cost=round(cost, 6) if cost is not None else None,
            )

            if tracer is not None:
                final_text = final if isinstance(final, str) else json.dumps(final, default=str)
                async with tracer.span(
                    SpanKind.REASONING,
                    "agent_output",
                    model=cfg.model,
                    provider=cfg.provider,
                    output_length=len(final_text),
                    has_recommendation=any(
                        kw in final_text.lower()
                        for kw in ("recommend", "suggest", "should", "consider", "action")
                    ),
                ):
                    pass

            if memory and cfg.memory.auto_save and thread:
                asyncio.create_task(
                    _safe_extract(
                        thread, memory, provider, context.run_id, cfg.name or "",
                        model=cfg.model or "",
                    ),
                )

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


async def _safe_extract(
    thread: list[Message],
    store: MemoryStore,
    provider: LLMProvider,
    run_id: str,
    agent_name: str,
    *,
    model: str,
) -> None:
    """Fire-and-forget episode extraction — never raises."""
    try:
        await extract_episode(
            thread,
            store,
            provider,
            model=model,
            run_id=run_id,
            agent_name=agent_name,
        )
    except Exception:
        logger.warning("episode_extraction_background_failed", run_id=run_id, exc_info=True)


def _insert_before_last_user(thread: list[Message], msg: Message) -> None:
    """Insert *msg* just before the last user message (tail-inject).

    Keeps the static prefix (system prompt + TBox priming) contiguous
    for KV-cache stability, and places dynamic content in recent context
    where the model's attention is strongest.
    """
    thread.insert(_find_tail_inject_point(thread), msg)


def _extract_user_question(thread: list[Message]) -> str | None:
    """Return the content of the last user message in the thread."""
    for msg in reversed(thread):
        if msg.role == "user" and msg.content:
            return str(msg.content)
    return None


_TRIVIAL_MAX_WORDS = 6


def _needs_context(question: str | None) -> bool:
    """Cheap gate: skip graph/memory injection for trivially short messages.

    Returns ``False`` for greetings, "thanks", single-word messages, etc.
    — avoiding KG lookups and memory recall on messages that don't need them.
    """
    if not question:
        return False
    words = question.split()
    return len(words) > _TRIVIAL_MAX_WORDS


def _resolve_provider(provider_name: str | None, context: RuntimeContext) -> LLMProvider:
    """Resolve the LLM provider via the factory."""
    factory = context.deps.provider_factory or context.extras.get("provider_factory")
    if factory is not None:
        return factory.create(provider_name or "")

    raise RuntimeError(
        f"No LLM provider factory in context. Cannot resolve provider '{provider_name}'. "
        "Ensure the container wires a LLMProviderFactory into context deps or extras."
    )
