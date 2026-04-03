"""Think-act-observe loop — the core agent iteration logic.

Uses a **tool-call budget** rather than a pure iteration cap.
``max_tool_rounds`` limits how many iterations may include tool calls.
After the budget is spent the loop makes one final LLM call *with tools
disabled* so the agent always produces a proper synthesis.

Tool calls within a single LLM response are executed **concurrently**
via ``asyncio.gather``.
"""

from __future__ import annotations

import asyncio
import json

import structlog

from remi.agent.config import AgentConfig, PhaseConfig
from remi.agent.conversation.compression import compress_tool_result
from remi.agent.conversation.thread import try_parse_json
from remi.agent.llm.types import LLMProvider, LLMRequest, TokenUsage, ToolCallRequest
from remi.agent.observe.types import Tracer
from remi.agent.observe.usage import LLMUsageLedger
from remi.agent.runtime.deps import OnEventCallback
from remi.agent.runtime.llm_bridge import build_llm_request, stream_llm_response
from remi.agent.runtime.tool_executor import ToolExecutor
from remi.agent.types import Message

logger = structlog.get_logger("remi.agent.loop")


def _build_phase_thresholds(
    phases: list[PhaseConfig],
) -> list[tuple[int, PhaseConfig]]:
    """Return (cumulative_iteration, phase) pairs for transition nudges."""
    thresholds: list[tuple[int, PhaseConfig]] = []
    cumulative = 0
    for phase in phases:
        cumulative += phase.max_iterations
        thresholds.append((cumulative, phase))
    return thresholds


def _serialize_result(result: object) -> str | int | float | bool:
    """Serialize a tool result for the emit callback."""
    if isinstance(result, (str, int, float, bool)):
        return result
    return json.dumps(result, default=str)


async def _execute_tool_call(
    tc: ToolCallRequest,
    iteration: int,
    tool_executor: ToolExecutor,
    emit: OnEventCallback,
) -> Message:
    """Execute a single tool call with event emission. Returns the tool Message."""
    await emit(
        "tool_call",
        {"tool": tc.name, "arguments": tc.arguments, "call_id": tc.id},
    )
    result = await tool_executor.execute(tc, iteration)
    await emit(
        "tool_result",
        {"tool": tc.name, "call_id": tc.id, "result": _serialize_result(result)},
    )
    compressed = compress_tool_result(tc.name, result)
    return Message(role="tool", name=tc.name, tool_call_id=tc.id, content=compressed)


async def run_agent_loop(
    *,
    cfg: AgentConfig,
    thread: list[Message],
    provider: LLMProvider,
    tool_executor: ToolExecutor,
    emit: OnEventCallback,
    tracer: Tracer | None,
    log: structlog.stdlib.BoundLogger,
    max_tool_rounds: int | None = None,
    routing_provider: LLMProvider | None = None,
    usage_ledger: LLMUsageLedger | None = None,
) -> tuple[list[Message], TokenUsage]:
    """Execute the think-act-observe loop.

    Returns the updated thread and cumulative token usage.
    """
    tool_round_budget = max_tool_rounds if max_tool_rounds is not None else cfg.max_iterations
    hard_cap = cfg.max_iterations
    total_iterations = 0
    tool_rounds_used = 0
    run_usage = TokenUsage()
    tool_defs = tool_executor.definitions
    produced_answer = False

    all_tool_defs = list(tool_defs)
    phase_thresholds = _build_phase_thresholds(cfg.phases)
    next_phase_idx = 0
    current_phase_name: str | None = cfg.phases[0].name if cfg.phases else None

    for iteration in range(hard_cap):
        total_iterations = iteration + 1

        if phase_thresholds and next_phase_idx < len(phase_thresholds):
            threshold, phase = phase_thresholds[next_phase_idx]
            if iteration >= threshold and next_phase_idx + 1 < len(phase_thresholds):
                next_phase_idx += 1
                _, next_phase = phase_thresholds[next_phase_idx]
                current_phase_name = next_phase.name
                nudge = next_phase.nudge or (
                    f"Phase transition: you should now be in the "
                    f"**{next_phase.name}** phase. {next_phase.description}"
                )
                thread.append(Message(role="system", content=nudge))

                if next_phase.tools:
                    allowed = set(next_phase.tools)
                    tool_defs = [td for td in all_tool_defs if td.name in allowed]
                    log.info(
                        "phase_tool_pruning",
                        phase=next_phase.name,
                        kept=len(tool_defs),
                        total=len(all_tool_defs),
                    )

                log.info(
                    "phase_transition",
                    from_phase=phase.name,
                    to_phase=next_phase.name,
                    iteration=iteration,
                )
                await emit(
                    "phase",
                    {
                        "phase": next_phase.name,
                        "iteration": iteration,
                        "description": next_phase.description,
                    },
                )

        budget_exhausted = tool_rounds_used >= tool_round_budget
        active_tools = None if budget_exhausted else (tool_defs or None)

        log.debug(
            "iteration_start",
            iteration=iteration,
            thread_length=len(thread),
            tools_enabled=active_tools is not None,
            tool_rounds_used=tool_rounds_used,
            tool_round_budget=tool_round_budget,
            phase=current_phase_name,
        )

        use_routing = (
            iteration > 0
            and active_tools is not None
            and cfg.tool_routing_model
            and routing_provider is not None
        )
        if use_routing and routing_provider is not None:
            iter_provider = routing_provider
        else:
            iter_provider = provider
        iter_model = cfg.tool_routing_model if use_routing else None

        if use_routing:
            log.info(
                "model_routing",
                iteration=iteration,
                routing_model=cfg.tool_routing_model,
                primary_model=cfg.model,
            )

        request = build_llm_request(
            cfg,
            thread,
            active_tools,
            model_override=iter_model,
        )

        response = await stream_llm_response(
            iter_provider,
            request,
            emit,
            iteration,
            tracer,
            cfg,
            usage_ledger=usage_ledger,
        )
        run_usage = run_usage + response.usage
        log.info(
            "llm_response",
            iteration=total_iterations,
            tool_calls=len(response.tool_calls),
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            has_content=bool(response.content),
            effective_model=request.model,
        )

        if not response.tool_calls:
            content = response.content or ""
            if cfg.response_format == "json":
                content = try_parse_json(content)
            thread.append(Message(role="assistant", content=content))
            produced_answer = True
            break

        tool_rounds_used += 1  # noqa: SIM113
        thread.append(
            Message(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls or None,
            )
        )

        tool_messages = await asyncio.gather(
            *[_execute_tool_call(tc, iteration, tool_executor, emit) for tc in response.tool_calls]
        )
        thread.extend(tool_messages)

    if not produced_answer:
        log.info("hard_cap_synthesis", iterations=total_iterations)
        synth_request = LLMRequest(
            model=cfg.model or "",
            messages=thread,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        synth_response = await stream_llm_response(
            provider,
            synth_request,
            emit,
            total_iterations,
            tracer,
            cfg,
            usage_ledger=usage_ledger,
        )
        run_usage = run_usage + synth_response.usage
        content = synth_response.content or ""
        thread.append(Message(role="assistant", content=content))

    return thread, run_usage
