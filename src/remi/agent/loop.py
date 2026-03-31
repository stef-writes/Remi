"""Think-act-observe loop — the core agent iteration logic.

Uses a **tool-call budget** rather than a pure iteration cap.
``max_tool_rounds`` (from the intent or config) limits how many
iterations may include tool calls.  After the budget is spent the loop
makes one final LLM call *with tools disabled* so the agent always
produces a proper synthesis rather than being silently truncated.
``max_iterations`` remains as a hard safety ceiling.
"""

from __future__ import annotations

import json

import structlog

from remi.agent.base import Message
from remi.agent.config import AgentConfig
from remi.agent.llm_bridge import OnEventCallback, build_llm_request, stream_llm_response
from remi.agent.thread import try_parse_json
from remi.agent.tool_executor import ToolExecutor
from remi.llm.ports import LLMProvider, LLMRequest, TokenUsage
from remi.observability.tracer import Tracer

logger = structlog.get_logger("remi.agent.loop")


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
) -> tuple[list[Message], TokenUsage]:
    """Execute the think-act-observe loop.

    *max_tool_rounds* caps how many iterations may invoke tools.
    After that many tool-using iterations, the next LLM call is sent
    without tools so the model must produce a text response.
    Falls back to ``cfg.max_iterations`` when not set.

    Returns the updated thread and cumulative token usage.
    """
    tool_round_budget = max_tool_rounds if max_tool_rounds is not None else cfg.max_iterations
    hard_cap = cfg.max_iterations
    total_iterations = 0
    tool_rounds_used = 0
    run_usage = TokenUsage()
    tool_defs = tool_executor.definitions
    produced_answer = False

    for iteration in range(hard_cap):
        total_iterations = iteration + 1

        # When the tool budget is spent, disable tools so the LLM
        # synthesizes a text answer instead of requesting more calls.
        budget_exhausted = tool_rounds_used >= tool_round_budget
        active_tools = None if budget_exhausted else (tool_defs or None)

        log.debug(
            "iteration_start",
            iteration=iteration,
            thread_length=len(thread),
            tools_enabled=active_tools is not None,
            tool_rounds_used=tool_rounds_used,
            tool_round_budget=tool_round_budget,
        )

        request = build_llm_request(cfg, thread, active_tools)

        response = await stream_llm_response(
            provider,
            request,
            emit,
            iteration,
            tracer,
            cfg,
        )
        run_usage = run_usage + response.usage
        log.info(
            "llm_response",
            iteration=total_iterations,
            tool_calls=len(response.tool_calls),
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            has_content=bool(response.content),
        )

        if not response.tool_calls:
            content = response.content or ""
            if cfg.response_format == "json":
                content = try_parse_json(content)
            thread.append(Message(role="assistant", content=content))
            produced_answer = True
            break

        tool_rounds_used += 1
        thread.append(
            Message(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls or None,
            )
        )
        for tc in response.tool_calls:
            await emit(
                "tool_call",
                {
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "call_id": tc.id,
                },
            )

            result = await tool_executor.execute(tc, iteration)

            thread.append(Message(role="tool", name=tc.name, tool_call_id=tc.id, content=result))
            await emit(
                "tool_result",
                {
                    "tool": tc.name,
                    "call_id": tc.id,
                    "result": result
                    if isinstance(result, (str, int, float, bool))
                    else json.dumps(result, default=str),
                },
            )

    # Safety net: if the hard cap was hit without an answer (shouldn't
    # normally happen with the budget logic above), force a synthesis.
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
        )
        run_usage = run_usage + synth_response.usage
        content = synth_response.content or ""
        thread.append(Message(role="assistant", content=content))

    return thread, run_usage
