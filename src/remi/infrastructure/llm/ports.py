"""LLM provider port — the model-agnostic interface that all LLM adapters implement.

Providers accept REMI-native types (Message, ToolDefinition) and handle
wire-format translation internally. Callers never deal with provider-specific
message or tool schemas.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from remi.domain.modules.base import Message
    from remi.domain.tools.ports import ToolDefinition


@dataclass(frozen=True)
class ToolCallRequest:
    """A single tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)


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
