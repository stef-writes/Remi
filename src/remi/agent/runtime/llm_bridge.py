"""LLM streaming bridge — streams provider responses with proper span management."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from remi.agent.config import AgentConfig
from remi.agent.llm.types import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
    ToolCallRequest,
    estimate_cost,
)
from remi.agent.observe.events import Event
from remi.agent.observe.types import SpanKind, Tracer, get_current_trace_id
from remi.agent.observe.usage import LLMUsageLedger, UsageRecord, UsageSource
from remi.agent.runtime.deps import OnEventCallback as OnEventCallback  # noqa: F401
from remi.agent.types import Message, ToolDefinition

logger = structlog.get_logger("remi.agent.llm")


@dataclass
class _ToolCallAccumulator:
    """Accumulates streaming tool call fragments into a complete ToolCallRequest."""

    id: str
    name: str
    arguments_json: str = ""


def build_llm_request(
    cfg: AgentConfig,
    thread: list[Message],
    tool_defs: list[ToolDefinition] | None,
    *,
    model_override: str | None = None,
) -> LLMRequest:
    """Build a typed LLM request from config and thread state."""
    return LLMRequest(
        model=model_override or cfg.model or "",
        messages=thread,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        tools=tool_defs if tool_defs else None,
    )


async def stream_llm_response(
    provider: LLMProvider,
    request: LLMRequest,
    emit: OnEventCallback,
    iteration: int,
    tracer: Tracer | None,
    cfg: AgentConfig,
    *,
    usage_ledger: LLMUsageLedger | None = None,
) -> LLMResponse:
    """Stream an LLM response, emitting deltas as they arrive."""
    content_parts: list[str] = []
    tool_accumulators: dict[str, _ToolCallAccumulator] = {}
    usage = TokenUsage()

    async def _do_stream() -> None:
        nonlocal usage
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            kwargs["tools"] = request.tools
        async for chunk in provider.stream(**kwargs):
            if chunk.type == "content_delta":
                content_parts.append(chunk.content)
                await emit("delta", {"content": chunk.content, "iteration": iteration})
            elif chunk.type == "tool_call_start":
                tool_accumulators[chunk.tool_call_id] = _ToolCallAccumulator(
                    id=chunk.tool_call_id,
                    name=chunk.tool_name,
                )
            elif chunk.type == "tool_call_delta":
                acc = tool_accumulators.get(chunk.tool_call_id)
                if acc is not None:
                    acc.arguments_json += chunk.tool_arguments_delta
            elif chunk.type == "done":
                usage = chunk.usage

    effective_model = request.model or cfg.model
    if tracer is not None:
        async with tracer.span(
            SpanKind.LLM_CALL,
            f"{cfg.provider}/{effective_model}",
            provider=cfg.provider,
            model=effective_model,
            iteration=iteration,
            message_count=len(request.messages),
            temperature=cfg.temperature,
            has_tools=bool(request.tools),
        ) as span_ctx:
            try:
                await _do_stream()
            except Exception:
                logger.error(
                    Event.LLM_STREAM_ERROR,
                    provider=cfg.provider,
                    model=cfg.model,
                    iteration=iteration,
                    exc_info=True,
                )
                raise
            span_ctx.set_attribute("has_tool_calls", bool(tool_accumulators))
            span_ctx.set_attribute("response_length", sum(len(p) for p in content_parts))
            if usage.total_tokens > 0:
                span_ctx.set_attribute("usage", usage.to_dict())
    else:
        try:
            await _do_stream()
        except Exception:
            logger.error(
                Event.LLM_STREAM_ERROR,
                provider=cfg.provider,
                model=cfg.model,
                iteration=iteration,
                exc_info=True,
            )
            raise

    assembled_tool_calls: list[ToolCallRequest] = []
    for acc in tool_accumulators.values():
        try:
            arguments = json.loads(acc.arguments_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                Event.LLM_TOOL_ARGS_ERROR,
                tool_name=acc.name,
                call_id=acc.id,
                raw_length=len(acc.arguments_json),
            )
            arguments = {"raw": acc.arguments_json}
        assembled_tool_calls.append(
            ToolCallRequest(
                id=acc.id,
                name=acc.name,
                arguments=arguments,
            )
        )

    if usage_ledger is not None and usage.total_tokens > 0:
        effective_model = request.model or cfg.model or ""
        cost = estimate_cost(effective_model, usage.prompt_tokens, usage.completion_tokens)
        usage_ledger.record(UsageRecord(
            source=UsageSource.AGENT,
            source_detail=cfg.name or "unknown",
            provider=cfg.provider or "",
            model=effective_model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_creation_tokens=usage.cache_creation_tokens,
            estimated_cost_usd=round(cost, 6) if cost is not None else None,
            trace_id=get_current_trace_id(),
        ))

    content = "".join(content_parts) or None
    return LLMResponse(
        content=content,
        model=request.model or cfg.model or "",
        usage=usage,
        tool_calls=assembled_tool_calls,
    )
