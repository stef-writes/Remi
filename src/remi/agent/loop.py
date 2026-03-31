"""Think-act-observe loop — the core agent iteration logic."""

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
) -> tuple[list[Message], TokenUsage]:
    """Execute the think-act-observe loop.

    Returns the updated thread and cumulative token usage.
    """
    total_iterations = 0
    run_usage = TokenUsage()
    tool_defs = tool_executor.definitions

    for iteration in range(cfg.max_iterations):
        total_iterations = iteration + 1
        log.debug("iteration_start", iteration=iteration, thread_length=len(thread))

        request = build_llm_request(cfg, thread, tool_defs or None)

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
            break

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

    # Synthesis turn if loop exhausted without a text response
    if total_iterations >= cfg.max_iterations:
        log.info("loop_exhausted", iterations=total_iterations)
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
