"""Anthropic adapter for the LLM provider port.

Translates REMI-neutral Message/ToolDefinition types into
Anthropic's wire format internally.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING, Any

from remi.infrastructure.llm.ports import LLMProvider, LLMResponse, ToolCallRequest

if TYPE_CHECKING:
    from remi.domain.modules.base import Message
    from remi.domain.tools.ports import ToolDefinition


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

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
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id or "",
                        "content": cls._as_str(msg.content),
                    }],
                })
                continue

            converted.append({
                "role": msg.role,
                "content": cls._as_str(msg.content),
            })

        return "\n\n".join(system_parts), converted

    @staticmethod
    def _tool_to_anthropic(defn: ToolDefinition) -> dict[str, Any]:
        return {
            "name": defn.name,
            "description": defn.description,
            "input_schema": defn.to_json_schema(),
        }

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
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "Anthropic provider requires the 'anthropic' package: pip install anthropic"
            ) from exc

        client = anthropic.AsyncAnthropic(api_key=self._api_key)

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

        usage: dict[str, int] = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.input_tokens,
                "completion_tokens": resp.usage.output_tokens,
                "total_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
            }

        return LLMResponse(
            content=content_text,
            model=resp.model,
            usage=usage,
            tool_calls=tool_calls,
        )
