"""LLM types — wire-format DTOs, provider port, and model metadata.

Defines the model-agnostic conversation types (Message, ToolCallRequest,
ToolDefinition) plus the abstract LLM provider interface. All packages
that interact with LLMs depend on these types; provider adapters implement
the LLMProvider ABC.
"""

from __future__ import annotations

import abc
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel
from pydantic import Field as PydanticField

# ---------------------------------------------------------------------------
# LLM wire types — the conversation vocabulary
# ---------------------------------------------------------------------------


class ToolCallRequest(BaseModel, frozen=True):
    """A single tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


class ToolArg(BaseModel, frozen=True):
    """A single named argument for a tool."""

    name: str
    description: str = ""
    required: bool = False
    type: str = "string"


class ToolDefinition(BaseModel, frozen=True):
    """Lean tool metadata — what the tool does and what args it takes."""

    name: str
    description: str
    args: list[ToolArg] = PydanticField(default_factory=list)

    def to_json_schema(self) -> dict[str, Any]:
        """Generate JSON Schema from args — used by LLM provider adapters."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for arg in self.args:
            properties[arg.name] = {
                "type": arg.type,
                "description": arg.description,
            }
            if arg.required:
                required.append(arg.name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def to_help_text(self) -> str:
        """Render tool as --help style text — compact, agent-friendly."""
        lines = [f"{self.name}: {self.description}"]
        if self.args:
            lines.append("  args:")
            for a in self.args:
                req = " (required)" if a.required else ""
                lines.append(f"    --{a.name}  [{a.type}] {a.description}{req}")
        return "\n".join(lines)


class Message(BaseModel, frozen=True):
    """A single entry in a conversation thread passed between agent nodes."""

    role: str
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCallRequest] | None = None
    metadata: dict[str, Any] = PydanticField(default_factory=dict)

__all__ = [
    "ToolCallRequest",
    "ToolArg",
    "ToolDefinition",
    "Message",
    "ProviderConfig",
    "ModelPricing",
    "ModelCapabilities",
    "TokenUsage",
    "LLMRequest",
    "LLMResponse",
    "LLMProvider",
    "StreamChunkType",
    "StreamChunk",
    "estimate_cost",
]


# ---------------------------------------------------------------------------
# Provider configuration — uniform across all adapters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderConfig:
    """Settings every LLM adapter receives at construction time."""

    api_key: str = ""
    base_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Model metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelPricing:
    """Per-million-token pricing for a single model."""

    input_per_1m: float
    output_per_1m: float


@dataclass(frozen=True)
class ModelCapabilities:
    """Static metadata for a model — limits, feature flags, pricing."""

    context_window: int
    max_output_tokens: int
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    pricing: ModelPricing | None = None


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    capabilities_fn: Callable[[str], ModelCapabilities] | None = None,
) -> float | None:
    """Return estimated cost in USD, or None if model pricing is unknown.

    If *capabilities_fn* is provided it is called to look up pricing;
    otherwise falls back to the legacy ``_FALLBACK_PRICING`` table.
    """
    pricing: ModelPricing | None = None
    if capabilities_fn is not None:
        caps = capabilities_fn(model)
        pricing = caps.pricing
    if pricing is None:
        pricing = _FALLBACK_PRICING.get(model)
    if pricing is None:
        return None
    return (
        prompt_tokens * pricing.input_per_1m / 1_000_000
        + completion_tokens * pricing.output_per_1m / 1_000_000
    )


# Kept as a fallback so callers without a provider instance still work.
_FALLBACK_PRICING: dict[str, ModelPricing] = {
    # Anthropic
    "claude-opus-4-20250514": ModelPricing(5.0, 25.0),
    "claude-opus-4-6": ModelPricing(5.0, 25.0),
    "claude-sonnet-4-20250514": ModelPricing(3.0, 15.0),
    "claude-sonnet-4-6": ModelPricing(3.0, 15.0),
    "claude-sonnet-4-5-20250929": ModelPricing(3.0, 15.0),
    "claude-haiku-4-5-20251001": ModelPricing(1.0, 5.0),
    # OpenAI
    "gpt-4o": ModelPricing(2.5, 10.0),
    "gpt-4o-mini": ModelPricing(0.15, 0.6),
    "gpt-4-turbo": ModelPricing(10.0, 30.0),
    # Google
    "gemini-2.0-flash": ModelPricing(0.1, 0.4),
    "gemini-1.5-pro": ModelPricing(1.25, 5.0),
}


# ---------------------------------------------------------------------------
# Token usage / request / response types
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel, frozen=True):
    """Token counts from a single LLM call or accumulated across a run."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
        )

    @classmethod
    def from_dict(cls, raw: dict[str, int]) -> TokenUsage:
        return cls(
            prompt_tokens=raw.get("prompt_tokens", 0),
            completion_tokens=raw.get("completion_tokens", 0),
            total_tokens=raw.get("total_tokens", 0),
            cache_read_tokens=raw.get("cache_read_tokens", 0),
            cache_creation_tokens=raw.get("cache_creation_tokens", 0),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
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


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------


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
                tool_arguments_delta=json.dumps(tc.arguments, default=str),
            )
            yield StreamChunk(type="tool_call_end", tool_call_id=tc.id)
        yield StreamChunk(type="done", usage=response.usage)

    @abc.abstractmethod
    def count_tokens(
        self,
        messages: list[Message],
        *,
        model: str,
        tools: list[ToolDefinition] | None = None,
    ) -> int:
        """Count tokens for the given messages + tools using a provider-native
        tokenizer (or best-available approximation)."""

    @abc.abstractmethod
    def model_capabilities(self, model: str) -> ModelCapabilities:
        """Return capabilities/limits for a model name."""
