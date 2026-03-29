"""OpenAI adapter for the LLM provider port.

Also serves as the base for any OpenAI-compatible API (Ollama, vLLM,
Together, Groq, etc.) by passing a custom ``base_url``.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from remi.infrastructure.llm.ports import LLMProvider, LLMResponse, ToolCallRequest

if TYPE_CHECKING:
    from remi.domain.modules.base import Message
    from remi.domain.tools.ports import ToolDefinition


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url

    # -- wire-format translation (REMI → OpenAI) ----------------------------

    @staticmethod
    def _message_to_openai(msg: Message) -> dict[str, Any]:
        entry: dict[str, Any] = {"role": msg.role}
        if isinstance(msg.content, str):
            entry["content"] = msg.content
        else:
            entry["content"] = json.dumps(msg.content, default=str)
        if msg.name:
            entry["name"] = msg.name
        if msg.tool_call_id:
            entry["tool_call_id"] = msg.tool_call_id
        return entry

    @staticmethod
    def _tool_to_openai(defn: ToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": defn.name,
                "description": defn.description,
                "parameters": defn.to_json_schema(),
            },
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
            import openai
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI provider requires the 'openai' package: pip install openai"
            ) from exc

        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

        openai_messages = [self._message_to_openai(m) for m in messages]

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = [self._tool_to_openai(t) for t in tools]

        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]

        usage: dict[str, int] = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }

        tool_calls: list[ToolCallRequest] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {"raw": tc.function.arguments}
                tool_calls.append(
                    ToolCallRequest(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    )
                )

        return LLMResponse(
            content=choice.message.content,
            model=resp.model,
            usage=usage,
            tool_calls=tool_calls,
        )
