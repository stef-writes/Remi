"""Anthropic adapter for the LLM provider port.

Translates REMI-neutral Message/ToolDefinition types into
Anthropic's wire format internally.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from remi.llm.ports import LLMProvider, LLMResponse, StreamChunk, TokenUsage, ToolCallRequest
from remi.models.chat import Message
from remi.models.tools import ToolDefinition


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client: Any = None

    # -- wire-format translation (REMI → Anthropic) --------------------------

    @staticmethod
    def _as_str(content: Any) -> str:
        return content if isinstance(content, str) else json.dumps(content, default=str)

    @classmethod
    def _split_system_and_messages(
        cls,
        messages: list[Message],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Anthropic expects a top-level ``system`` param, not a system message."""
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_parts.append(cls._as_str(msg.content))
                continue

            if msg.role == "tool":
                converted.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id or "",
                                "content": cls._as_str(msg.content),
                            }
                        ],
                    }
                )
                continue

            if msg.role == "assistant" and msg.tool_calls:
                blocks: list[dict[str, Any]] = []
                if msg.content:
                    blocks.append({"type": "text", "text": cls._as_str(msg.content)})
                for tc in msg.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                converted.append({"role": "assistant", "content": blocks})
                continue

            converted.append(
                {
                    "role": msg.role,
                    "content": cls._as_str(msg.content),
                }
            )

        return "\n\n".join(system_parts), converted

    @staticmethod
    def _tool_to_anthropic(defn: ToolDefinition) -> dict[str, Any]:
        return {
            "name": defn.name,
            "description": defn.description,
            "input_schema": defn.to_json_schema(),
        }

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise RuntimeError(
                    "Anthropic provider requires the 'anthropic' package: pip install anthropic"
                ) from exc
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    # -- LLMProvider interface ------------------------------------------------

    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        system_prompt, anthropic_messages = self._split_system_and_messages(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [self._tool_to_anthropic(t) for t in tools]

        resp = await client.messages.create(**kwargs)

        content_text: str | None = None
        tool_calls: list[ToolCallRequest] = []

        for block in resp.content:
            if block.type == "text":
                content_text = block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.id or uuid.uuid4().hex,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        usage = (
            TokenUsage(
                prompt_tokens=resp.usage.input_tokens,
                completion_tokens=resp.usage.output_tokens,
                total_tokens=resp.usage.input_tokens + resp.usage.output_tokens,
            )
            if resp.usage
            else TokenUsage()
        )

        return LLMResponse(
            content=content_text,
            model=resp.model,
            usage=usage,
            tool_calls=tool_calls,
        )

    async def stream(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()
        system_prompt, anthropic_messages = self._split_system_and_messages(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [self._tool_to_anthropic(t) for t in tools]

        current_tool_id = ""
        current_tool_name = ""
        prompt_tokens = 0
        completion_tokens = 0

        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if hasattr(block, "type") and block.type == "tool_use":
                        current_tool_id = block.id or uuid.uuid4().hex
                        current_tool_name = block.name
                        yield StreamChunk(
                            type="tool_call_start",
                            tool_call_id=current_tool_id,
                            tool_name=current_tool_name,
                        )
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if hasattr(delta, "type"):
                        if delta.type == "text_delta":
                            yield StreamChunk(type="content_delta", content=delta.text)
                        elif delta.type == "input_json_delta":
                            yield StreamChunk(
                                type="tool_call_delta",
                                tool_call_id=current_tool_id,
                                tool_arguments_delta=delta.partial_json,
                            )
                elif event.type == "content_block_stop":
                    if current_tool_id:
                        yield StreamChunk(type="tool_call_end", tool_call_id=current_tool_id)
                        current_tool_id = ""
                        current_tool_name = ""
                elif event.type == "message_delta":
                    if hasattr(event, "usage") and event.usage:
                        completion_tokens = getattr(event.usage, "output_tokens", 0)
                elif event.type == "message_start":
                    if hasattr(event, "message") and hasattr(event.message, "usage"):
                        prompt_tokens = getattr(event.message.usage, "input_tokens", 0)

        yield StreamChunk(
            type="done",
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )
