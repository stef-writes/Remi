"""In-memory tool registry."""

from __future__ import annotations

from remi.domain.tools.ports import ToolDefinition, ToolFn, ToolRegistry


class InMemoryToolRegistry(ToolRegistry):
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolFn, ToolDefinition]] = {}

    def register(
        self, name: str, fn: ToolFn, definition: ToolDefinition
    ) -> None:
        self._tools[name] = (fn, definition)

    def get(self, name: str) -> tuple[ToolFn, ToolDefinition] | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        return [defn for _, defn in self._tools.values()]

    def list_definitions(self, names: list[str] | None = None) -> list[ToolDefinition]:
        result: list[ToolDefinition] = []
        for tool_name, (_, defn) in self._tools.items():
            if names is not None and tool_name not in names:
                continue
            result.append(defn)
        return result

    def has(self, name: str) -> bool:
        return name in self._tools
