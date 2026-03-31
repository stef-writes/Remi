"""LLM streaming bridge — streams provider responses with proper span management."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from remi.agent.config import AgentConfig
from remi.llm.ports import LLMProvider, LLMRequest, LLMResponse, TokenUsage, ToolCallRequest
from remi.models.chat import Message
from remi.models.tools import ToolDefinition
from remi.models.trace import SpanKind
from remi.observability.events import Event
from remi.observability.tracer import Tracer

logger = structlog.get_logger("remi.agent.llm")


class OnEventCallback(Protocol):
    """Typed callback for agent streaming events."""

    async def __call__(self, event_type: str, data: dict[str, Any]) -> None: ...


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
) -> LLMRequest:
    """Build a typed LLM request from config and thread state."""
    return LLMRequest(
        model=cfg.model or "",
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
) -> LLMResponse:
    """Stream an LLM response, emitting deltas as they arrive.

    When a tracer is provided, the entire stream is wrapped in a properly
    managed span that correctly marks ERROR on exception.
    """
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

    if tracer is not None:
        async with tracer.span(
            SpanKind.LLM_CALL,
            f"{cfg.provider}/{cfg.model}",
            provider=cfg.provider,
            model=cfg.model,
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

    content = "".join(content_parts) or None
    return LLMResponse(
        content=content,
        model=cfg.model or "",
        usage=usage,
        tool_calls=assembled_tool_calls,
    )
