"""Tool registry port — maps tool names to callables with runtime metadata.

Tool metadata is lightweight and environment-driven, not JSON Schema.
Each tool declares its args as a flat list of (name, description, required)
tuples — the same info you'd get from --help. LLM providers that need
JSON Schema (OpenAI function calling, etc.) generate it on demand from
this lean representation.
"""

from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

ToolFn = Callable[[dict[str, Any]], Awaitable[Any]]


class ToolArg(BaseModel, frozen=True):
    """A single named argument for a tool."""

    name: str
    description: str = ""
    required: bool = False
    type: str = "string"


class ToolDefinition(BaseModel, frozen=True):
    """Lean tool metadata — what the tool does and what args it takes.

    This is the canonical form. Provider adapters convert to JSON Schema
    or whatever wire format they need.
    """

    name: str
    description: str
    args: list[ToolArg] = Field(default_factory=list)

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


class ToolRegistry(abc.ABC):
    @abc.abstractmethod
    def register(
        self, name: str, fn: ToolFn, definition: ToolDefinition
    ) -> None: ...

    @abc.abstractmethod
    def get(self, name: str) -> tuple[ToolFn, ToolDefinition] | None: ...

    @abc.abstractmethod
    def list_tools(self) -> list[ToolDefinition]: ...

    @abc.abstractmethod
    def list_definitions(self, names: list[str] | None = None) -> list[ToolDefinition]:
        """Return tool definitions, optionally filtered by name."""
        ...

    @abc.abstractmethod
    def has(self, name: str) -> bool: ...
