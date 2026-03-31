"""OpenAI adapter for the LLM provider port.

Also serves as the base for any OpenAI-compatible API (Ollama, vLLM,
Together, Groq, etc.) by passing a custom ``base_url``.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from remi.llm.ports import LLMProvider, LLMResponse, StreamChunk, TokenUsage, ToolCallRequest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from remi.models.chat import Message
    from remi.models.tools import ToolDefinition


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url
        self._client: Any = None

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
        if msg.role == "assistant" and msg.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, default=str),
                    },
                }
                for tc in msg.tool_calls
            ]
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

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as exc:
                raise RuntimeError(
                    "OpenAI provider requires the 'openai' package: pip install openai"
                ) from exc
            self._client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
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

        usage = (
            TokenUsage(
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
                total_tokens=resp.usage.total_tokens,
            )
            if resp.usage
            else TokenUsage()
        )

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
        openai_messages = [self._message_to_openai(m) for m in messages]

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = [self._tool_to_openai(t) for t in tools]

        active_tool_calls: dict[int, dict[str, str]] = {}
        response_stream = await client.chat.completions.create(**kwargs)

        async for chunk in response_stream:
            choice = chunk.choices[0] if chunk.choices else None
            if choice and choice.delta:
                delta = choice.delta
                if delta.content:
                    yield StreamChunk(type="content_delta", content=delta.content)
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in active_tool_calls:
                            active_tool_calls[idx] = {
                                "id": tc_delta.id or "",
                                "name": tc_delta.function.name
                                if tc_delta.function and tc_delta.function.name
                                else "",
                                "arguments": "",
                            }
                            if active_tool_calls[idx]["id"]:
                                yield StreamChunk(
                                    type="tool_call_start",
                                    tool_call_id=active_tool_calls[idx]["id"],
                                    tool_name=active_tool_calls[idx]["name"],
                                )
                        if tc_delta.function and tc_delta.function.arguments:
                            active_tool_calls[idx]["arguments"] += tc_delta.function.arguments
                            yield StreamChunk(
                                type="tool_call_delta",
                                tool_call_id=active_tool_calls[idx]["id"],
                                tool_arguments_delta=tc_delta.function.arguments,
                            )

            if chunk.usage:
                usage = TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                )
                for tc_data in active_tool_calls.values():
                    yield StreamChunk(type="tool_call_end", tool_call_id=tc_data["id"])
                yield StreamChunk(type="done", usage=usage)
