"""LLM provider port — the model-agnostic interface that all LLM adapters implement.

Providers accept REMI-native types (Message, ToolDefinition) and handle
wire-format translation internally. Callers never deal with provider-specific
message or tool schemas.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel
from pydantic import Field as PydanticField

from remi.models.chat import Message, ToolCallRequest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from remi.models.tools import ToolDefinition

__all__ = ["Message", "ToolCallRequest", "TokenUsage", "LLMRequest", "LLMResponse", "LLMProvider"]


class TokenUsage(BaseModel, frozen=True):
    """Token counts from a single LLM call or accumulated across a run."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    @classmethod
    def from_dict(cls, raw: dict[str, int]) -> TokenUsage:
        return cls(
            prompt_tokens=raw.get("prompt_tokens", 0),
            completion_tokens=raw.get("completion_tokens", 0),
            total_tokens=raw.get("total_tokens", 0),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


class LLMRequest(BaseModel, frozen=True):
    """Typed parameters for an LLM call — replaces raw dict[str, Any]."""

    model: str
    messages: list[Any] = PydanticField(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 1024
    tools: list[Any] | None = None


class LLMResponse(BaseModel):
    """Complete (non-streaming) response from an LLM provider."""

    content: str | None = None
    model: str = ""
    usage: TokenUsage = PydanticField(default_factory=TokenUsage)
    tool_calls: list[ToolCallRequest] = PydanticField(default_factory=list)


StreamChunkType = Literal[
    "content_delta",
    "tool_call_start",
    "tool_call_delta",
    "tool_call_end",
    "done",
]


@dataclass
class StreamChunk:
    """A single chunk emitted during streaming.

    Stays a dataclass — it's ephemeral, never persisted or nested in
    Pydantic models. Just flows through the streaming pipeline.
    """

    type: StreamChunkType
    content: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    tool_arguments_delta: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)


class LLMProvider(abc.ABC):
    """Abstract LLM provider. Each adapter converts REMI-neutral types
    to its own wire format internally."""

    @abc.abstractmethod
    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse: ...

    async def stream(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream LLM response as chunks. Default: fall back to complete()."""
        response = await self.complete(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )
        if response.content:
            yield StreamChunk(type="content_delta", content=response.content)
        for tc in response.tool_calls:
            yield StreamChunk(
                type="tool_call_start",
                tool_call_id=tc.id,
                tool_name=tc.name,
            )
            yield StreamChunk(
                type="tool_call_delta",
                tool_call_id=tc.id,
                tool_arguments_delta=__import__("json").dumps(tc.arguments, default=str),
            )
            yield StreamChunk(type="tool_call_end", tool_call_id=tc.id)
        yield StreamChunk(type="done", usage=response.usage)
