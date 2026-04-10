"""Think-act-observe loop — the core agent iteration logic.

Uses a **tool-call budget** rather than a pure iteration cap.
``max_tool_rounds`` limits how many iterations may include tool calls.
After the budget is spent the loop makes one final LLM call *with tools
disabled* so the agent always produces a proper synthesis.

Tool calls within a single LLM response are executed **concurrently**
via ``asyncio.gather``.

The loop maintains a **scratchpad** — a rolling system message at the
tail of the thread that keeps the agent's working plan in recent
context.  This is the Manus "todo.md" pattern: instead of relying on
the model to hold its plan in memory across a growing context window,
we materialize it as a message that the model sees on every iteration.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from typing import Any

import structlog

from remi.agent.config import AgentConfig, PhaseConfig
from remi.agent.llm.types import LLMProvider, LLMRequest, TokenUsage, ToolCallRequest
from remi.agent.memory import MemoryStore
from remi.agent.observe.types import Tracer
from remi.agent.observe.usage import LLMUsageLedger
from remi.agent.runtime.conversation.compaction import (
    CompactionLevel,
    compact_thread,
    should_compact,
    summarize_old_exchanges,
)
from remi.agent.runtime.conversation.compression import compress_and_offload
from remi.agent.runtime.conversation.thread import try_parse_json
from remi.agent.runtime.deps import OnEventCallback
from remi.agent.runtime.llm_bridge import build_llm_request, stream_llm_response
from remi.agent.runtime.tool_executor import ToolExecutor
from remi.agent.types import Message

logger = structlog.get_logger("remi.agent.loop")

_SCRATCHPAD_TAG = "[scratchpad]"


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


_TOOL_HEARTBEAT_INTERVAL = 3.0  # seconds between heartbeat ticks

# ---------------------------------------------------------------------------
# Artifact extraction — __artifact__ protocol
# ---------------------------------------------------------------------------

_ARTIFACT_LINE_RE = re.compile(r'\{"__artifact__":\s*(\{.*\})\s*\}')


def _extract_artifacts(text: str) -> tuple[str, list[dict]]:
    """Scan tool output for __artifact__ JSON lines.

    Returns (cleaned_text, artifacts) where cleaned_text has the artifact
    lines stripped so they don't appear in the displayed tool result.
    """
    if "__artifact__" not in text:
        return text, []

    artifacts: list[dict] = []
    clean_lines: list[str] = []
    for line in text.splitlines():
        m = _ARTIFACT_LINE_RE.search(line)
        if m:
            try:
                artifacts.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                clean_lines.append(line)
        else:
            clean_lines.append(line)
    return "\n".join(clean_lines), artifacts



async def _execute_tool_call(
    tc: ToolCallRequest,
    iteration: int,
    tool_executor: ToolExecutor,
    emit: OnEventCallback,
    memory: MemoryStore | None = None,
    memory_namespace: str = "",
    infer_result_schema: Callable[[str, dict[str, Any]], str | None] | None = None,
) -> Message:
    """Execute a single tool call with event emission. Returns the tool Message."""
    result_schema = infer_result_schema(tc.name, tc.arguments) if infer_result_schema else None

    await emit(
        "tool_call",
        {"tool": tc.name, "arguments": tc.arguments, "call_id": tc.id},
    )

    async def _heartbeat() -> None:
        elapsed = 0.0
        while True:
            await asyncio.sleep(_TOOL_HEARTBEAT_INTERVAL)
            elapsed += _TOOL_HEARTBEAT_INTERVAL
            await emit(
                "tool_running",
                {"tool": tc.name, "call_id": tc.id, "elapsed_s": elapsed},
            )

    heartbeat_task = asyncio.create_task(_heartbeat())
    try:
        result = await tool_executor.execute(tc, iteration)
    finally:
        heartbeat_task.cancel()

    # Extract __artifact__ lines from string results before emitting.
    artifacts: list[dict] = []
    display_result = result
    if isinstance(result, str):
        display_result, artifacts = _extract_artifacts(result)

    tool_result_payload: dict = {
        "tool": tc.name,
        "call_id": tc.id,
        "result": _serialize_result(display_result),
    }
    if result_schema:
        tool_result_payload["result_schema"] = result_schema

    await emit("tool_result", tool_result_payload)

    # Emit each extracted artifact as a separate event.
    for artifact in artifacts:
        await emit("artifact", {"call_id": tc.id, "tool": tc.name, "artifact": artifact})

    compressed = await compress_and_offload(
        tc.name, tc.id, display_result, memory, memory_namespace
    )
    return Message(role="tool", name=tc.name, tool_call_id=tc.id, content=compressed)


def _build_scratchpad(
    iteration: int,
    tool_round_budget: int,
    tool_rounds_used: int,
    phase_name: str | None,
    tool_names_called: list[str],
    last_assistant_text: str | None,
) -> str:
    """Build the scratchpad system message for the current iteration.

    Keeps the agent's working state in recent context — the "todo.md"
    pattern.  The model sees this on every iteration so it never loses
    track of progress even in long tool-call chains.
    """
    parts = [f"{_SCRATCHPAD_TAG}"]
    parts.append(f"Iteration {iteration + 1} | tools used {tool_rounds_used}/{tool_round_budget}")
    if phase_name:
        parts.append(f"Phase: {phase_name}")
    if tool_names_called:
        parts.append(f"Tools called this run: {', '.join(dict.fromkeys(tool_names_called))}")
    if last_assistant_text:
        trimmed = last_assistant_text[:300]
        if len(last_assistant_text) > 300:
            trimmed += "…"
        parts.append(f"Last reasoning: {trimmed}")
    remaining = tool_round_budget - tool_rounds_used
    if remaining <= 2 and remaining > 0:
        parts.append(f"⚠ {remaining} tool round(s) remaining — begin synthesizing")
    elif remaining <= 0:
        parts.append("⚠ Tool budget spent — produce your final answer now")
    return "\n".join(parts)


def _remove_previous_scratchpad(thread: list[Message]) -> None:
    """Strip the previous scratchpad message from the thread (if any)."""
    for i in range(len(thread) - 1, -1, -1):
        msg = thread[i]
        if (
            msg.role == "system"
            and isinstance(msg.content, str)
            and msg.content.startswith(_SCRATCHPAD_TAG)
        ):
            thread.pop(i)
            return


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
    max_tokens: int | None = None,
    routing_provider: LLMProvider | None = None,
    compaction_provider: LLMProvider | None = None,
    usage_ledger: LLMUsageLedger | None = None,
    memory: MemoryStore | None = None,
    memory_namespace: str = "",
    context_budget: int = 0,
    infer_result_schema: Callable[[str, dict[str, Any]], str | None] | None = None,
) -> tuple[list[Message], TokenUsage]:
    """Execute the think-act-observe loop.

    ``context_budget`` is the model's context window in tokens.  When > 0,
    the loop checks for compaction before each LLM call and summarizes
    old exchanges if the thread is approaching the limit.

    ``max_tokens`` is a cumulative token budget for the entire run.
    When exceeded the loop forces a final synthesis call (same path as
    tool-round exhaustion) and returns.

    Returns the updated thread and cumulative token usage.
    """
    tool_round_budget = max_tool_rounds if max_tool_rounds is not None else cfg.max_iterations
    hard_cap = cfg.max_iterations
    total_iterations = 0
    tool_rounds_used = 0
    run_usage = TokenUsage()
    tool_defs = tool_executor.definitions
    produced_answer = False

    phase_thresholds = _build_phase_thresholds(cfg.phases)
    next_phase_idx = 0
    current_phase_name: str | None = cfg.phases[0].name if cfg.phases else None
    tool_names_called: list[str] = []
    last_assistant_text: str | None = None

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
                    preferred = ", ".join(next_phase.tools)
                    thread.append(
                        Message(
                            role="system",
                            content=(
                                f"Preferred tools for {next_phase.name} phase: {preferred}. "
                                "Focus on these tools but all tools remain available."
                            ),
                        )
                    )
                    log.info(
                        "phase_tool_hint",
                        phase=next_phase.name,
                        preferred=next_phase.tools,
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

        if iteration > 0 and tool_round_budget > 1:
            _remove_previous_scratchpad(thread)
            scratchpad = _build_scratchpad(
                iteration=iteration,
                tool_round_budget=tool_round_budget,
                tool_rounds_used=tool_rounds_used,
                phase_name=current_phase_name,
                tool_names_called=tool_names_called,
                last_assistant_text=last_assistant_text,
            )
            thread.append(Message(role="system", content=scratchpad))

        if context_budget > 0:
            level = should_compact(thread, context_budget)
            if level != CompactionLevel.NONE:
                _compaction_provider = compaction_provider or provider
                _compaction_model = cfg.compaction_model or cfg.model
                if level == CompactionLevel.COMPACT:
                    thread = await compact_thread(
                        thread, _compaction_provider, context_budget, model=_compaction_model
                    )
                else:
                    thread = await summarize_old_exchanges(
                        thread, _compaction_provider, context_budget, model=_compaction_model
                    )

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

        if max_tokens is not None and run_usage.total_tokens >= max_tokens:
            log.warning(
                "token_budget_exceeded",
                total_tokens=run_usage.total_tokens,
                budget=max_tokens,
                iteration=total_iterations,
            )
            content = response.content or ""
            _remove_previous_scratchpad(thread)
            thread.append(Message(role="assistant", content=content))
            produced_answer = bool(content)
            break

        if not response.tool_calls:
            content = response.content or ""
            if cfg.response_format == "json":
                content = try_parse_json(content)
            _remove_previous_scratchpad(thread)
            thread.append(Message(role="assistant", content=content))
            produced_answer = True
            break

        tool_rounds_used += 1  # noqa: SIM113
        last_assistant_text = response.content or None
        tool_names_called.extend(tc.name for tc in response.tool_calls)
        thread.append(
            Message(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls or None,
            )
        )

        tool_messages = await asyncio.gather(
            *[
                _execute_tool_call(
                    tc,
                    iteration,
                    tool_executor,
                    emit,
                    memory=memory,
                    memory_namespace=memory_namespace,
                    infer_result_schema=infer_result_schema,
                )
                for tc in response.tool_calls
            ]
        )
        thread.extend(tool_messages)

    if not produced_answer:
        _remove_previous_scratchpad(thread)
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
