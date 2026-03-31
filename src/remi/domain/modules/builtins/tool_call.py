"""ToolCall module — executes a registered tool function inside the graph."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from remi.domain.modules.base import BaseModule, ModuleOutput

if TYPE_CHECKING:
    from remi.runtime.context.runtime_context import RuntimeContext


class ToolCallModule(BaseModule):
    """Invokes a named tool from the tool registry.

    Config keys:
        tool:   name of the registered tool (e.g. "sql_query", "http_get")
        args:   static arguments merged with upstream inputs
    """

    kind = "tool_call"

    async def run(self, inputs: dict[str, Any], context: RuntimeContext) -> ModuleOutput:
        registry = context.extras.get("tool_registry")
        if registry is None:
            raise RuntimeError("No tool_registry in context extras")

        tool_name = self.config.get("tool", "")
        entry = registry.get(tool_name)
        if entry is None:
            raise RuntimeError(f"Tool not found in registry: {tool_name!r}")

        fn, _ = entry

        static_args = dict(self.config.get("args", {}))
        flat_inputs: dict[str, Any] = {}
        for val in inputs.values():
            if isinstance(val, dict):
                flat_inputs.update(val)
            else:
                flat_inputs["input"] = val

        merged_args = {**static_args, **flat_inputs}
        result = await fn(merged_args)

        return ModuleOutput(
            value=result,
            contract="tool_result",
            metadata={"tool": tool_name},
        )
