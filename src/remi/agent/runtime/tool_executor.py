"""ToolExecutor — unified tool dispatch with tracing and error handling."""

from __future__ import annotations

import json
import traceback as _traceback
from typing import Any, Protocol

import structlog

from remi.agent.config import AgentConfig
from remi.agent.llm.types import ToolCallRequest
from remi.agent.observe.types import SpanKind, Tracer
from remi.agent.runtime.deps import RuntimeContext
from remi.agent.types import ToolDefinition, ToolResult


class ToolExecuteFn(Protocol):
    """Typed protocol for the tool execution callback."""

    async def __call__(self, name: str, arguments: dict[str, Any]) -> Any: ...


class ToolExecutor:
    """Resolves, executes, and traces tool calls for an agent run."""

    def __init__(
        self,
        definitions: list[ToolDefinition],
        execute_fn: ToolExecuteFn | None,
        tracer: Tracer | None,
        log: structlog.stdlib.BoundLogger,
    ) -> None:
        self._definitions = definitions
        self._execute_fn = execute_fn
        self._tracer = tracer
        self._log = log

    @property
    def definitions(self) -> list[ToolDefinition]:
        return self._definitions

    async def execute(
        self,
        tc: ToolCallRequest,
        iteration: int,
    ) -> Any:
        """Execute a single tool call, with tracing if available."""
        self._log.info("tool_call_start", tool=tc.name, call_id=tc.id, iteration=iteration)

        if self._tracer is not None:
            async with self._tracer.span(
                SpanKind.TOOL_CALL,
                tc.name,
                tool_name=tc.name,
                arguments=tc.arguments,
                call_id=tc.id,
                iteration=iteration,
            ) as tool_ctx:
                result = await self._run(tc)
                tool_ctx.set_attribute("result_preview", _truncate(result, 500))
        else:
            result = await self._run(tc)

        has_error = (isinstance(result, ToolResult) and not result.ok) or (
            isinstance(result, dict) and bool(result.get("error"))
        )
        self._log.info(
            "tool_call_done",
            tool=tc.name,
            call_id=tc.id,
            iteration=iteration,
            ok=not has_error,
        )
        return result

    async def _run(self, tc: ToolCallRequest) -> Any:
        try:
            if self._execute_fn is not None:
                return await self._execute_fn(tc.name, tc.arguments)
            return {"error": f"Tool {tc.name} not available"}
        except Exception as exc:
            self._log.error(
                "tool_call_error",
                tool=tc.name,
                call_id=tc.id,
                error=str(exc),
            )
            return {"error": str(exc), "traceback": _traceback.format_exc()}


def build_tool_set(
    cfg: AgentConfig, context: RuntimeContext, *, mode: str = "agent"
) -> tuple[list[ToolDefinition], ToolExecuteFn | None]:
    """Build tool definitions and an executor scoped to declared tools."""
    registry = context.deps.tool_registry or context.extras.get("tool_registry")
    mode_tools = cfg.tools_for_mode(mode)
    if not registry or not mode_tools:
        return [], None

    tool_names = [t.name for t in mode_tools]
    definitions = registry.list_definitions(names=tool_names)
    tool_configs = {t.name: t.config for t in mode_tools}
    sandbox_session_id = context.params.sandbox_session_id or context.extras.get(
        "sandbox_session_id"
    )

    async def execute(name: str, arguments: dict[str, Any]) -> Any:
        entry = registry.get(name)
        if entry is None:
            return {"error": f"Tool '{name}' not found"}
        fn, _ = entry
        merged = {**tool_configs.get(name, {}), **arguments}
        if name in ("python", "bash") and sandbox_session_id:
            merged.setdefault("session_id", sandbox_session_id)
        return await fn(merged)

    return definitions, execute


def build_tool_set_for_names(
    tool_names: list[str],
    context: RuntimeContext,
) -> tuple[list[ToolDefinition], ToolExecuteFn | None]:
    """Build a tool set from an explicit list of tool names."""
    registry = context.deps.tool_registry or context.extras.get("tool_registry")
    if not registry or not tool_names:
        return [], None

    definitions = registry.list_definitions(names=tool_names)
    sandbox_session_id = context.params.sandbox_session_id or context.extras.get(
        "sandbox_session_id"
    )

    async def execute(name: str, arguments: dict[str, Any]) -> Any:
        entry = registry.get(name)
        if entry is None:
            return {"error": f"Tool '{name}' not found"}
        fn, _ = entry
        merged = dict(arguments)
        if name in ("python", "bash") and sandbox_session_id:
            merged.setdefault("session_id", sandbox_session_id)
        return await fn(merged)

    return definitions, execute


def _truncate(value: Any, max_len: int = 500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:max_len] + ("..." if len(text) > max_len else "")
