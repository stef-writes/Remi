"""ToolExecutor — unified tool dispatch with tracing and error handling.

``resolve_agent_tools`` reads the agent's ``ToolRef`` list, resolves each
through the ``ToolCatalog`` (or falls back to plain ``ToolRegistry``),
and returns a list of ``ToolBinding`` instances with agent-specific config,
description overrides, and context injection baked in.

``ToolExecutor`` wraps the bindings with tracing and error handling for
use in the agent loop.
"""

from __future__ import annotations

import json
import traceback as _traceback
from typing import Any

import structlog

from remi.agent.config import AgentConfig, ToolRef
from remi.agent.llm.types import ToolCallRequest
from remi.agent.observe.types import SpanKind, Tracer
from remi.agent.runtime.deps import RuntimeContext
from remi.agent.types import ToolBinding, ToolCatalog, ToolDefinition, ToolResult


class ToolExecutor:
    """Dispatches tool calls to their ``ToolBinding`` closures with tracing."""

    def __init__(
        self,
        bindings: list[ToolBinding],
        tracer: Tracer | None,
        log: structlog.stdlib.BoundLogger,
    ) -> None:
        self._bindings: dict[str, ToolBinding] = {
            b.definition.name: b for b in bindings
        }
        self._definitions = [b.definition for b in bindings]
        self._tracer = tracer
        self._log = log

    @classmethod
    def from_bindings(
        cls,
        bindings: list[ToolBinding],
        tracer: Tracer | None,
        log: structlog.stdlib.BoundLogger,
    ) -> ToolExecutor:
        """Construct from resolved bindings."""
        return cls(bindings, tracer, log)

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
            binding = self._bindings.get(tc.name)
            if binding is not None:
                return await binding.execute(tc.arguments)
            return {"error": f"Tool {tc.name} not available"}
        except Exception as exc:
            self._log.error(
                "tool_call_error",
                tool=tc.name,
                call_id=tc.id,
                error=str(exc),
            )
            return {"error": str(exc), "traceback": _traceback.format_exc()}


# ---------------------------------------------------------------------------
# Resolve agent tools via ToolCatalog (or ToolRegistry fallback)
# ---------------------------------------------------------------------------


def _build_context_values(context: RuntimeContext) -> dict[str, Any]:
    """Build the flat context-value dict available for ToolRef.inject."""
    values: dict[str, Any] = {"workspace_id": context.workspace_id}
    sid = context.params.sandbox_session_id or context.extras.get("sandbox_session_id")
    if sid:
        values["sandbox_session_id"] = sid
    if context.scope.entity_id:
        values["scope_entity_id"] = context.scope.entity_id
    if context.scope.entity_type:
        values["scope_entity_type"] = context.scope.entity_type
    if context.scope.tool_scope:
        values.update(context.scope.tool_scope)
    return values


def resolve_agent_tools(
    cfg: AgentConfig,
    context: RuntimeContext,
    *,
    mode: str = "agent",
) -> list[ToolBinding]:
    """Resolve the agent's declared tools into bound capabilities.

    Each ``ToolRef`` in the agent's mode-specific tool list is resolved
    through the ``ToolCatalog`` into a self-contained ``ToolBinding``
    with config, description, and context injection baked in.

    ``caller_agent`` is injected into context values so that tools
    like ``delegate_to_agent`` can identify the calling agent.
    """
    registry = context.deps.tool_registry or context.extras.get("tool_registry")
    mode_tools = cfg.tools_for_mode(mode)
    if not registry or not mode_tools:
        return []

    if not isinstance(registry, ToolCatalog):
        return _resolve_via_legacy(registry, mode_tools, context, cfg.name)

    ctx_values = _build_context_values(context)
    if cfg.name:
        ctx_values["caller_agent"] = cfg.name
    bindings: list[ToolBinding] = []
    for ref in mode_tools:
        binding = registry.resolve(
            ref.name,
            agent_config=ref.config or None,
            agent_description=ref.description,
            inject=ref.inject or None,
            context_values=ctx_values,
        )
        if binding is not None:
            bindings.append(binding)
    return bindings


def _resolve_via_legacy(
    registry: Any,
    mode_tools: list[ToolRef],
    context: RuntimeContext,
    agent_name: str = "",
) -> list[ToolBinding]:
    """Fallback when registry is a plain ToolRegistry, not a ToolCatalog."""
    ctx_values = _build_context_values(context)
    if agent_name:
        ctx_values["caller_agent"] = agent_name
    bindings: list[ToolBinding] = []
    for ref in mode_tools:
        entry = registry.get(ref.name)
        if entry is None:
            continue
        fn, base_def = entry
        definition = base_def
        if ref.description:
            definition = base_def.model_copy(update={"description": ref.description})

        cfg_dict = ref.config or {}
        inject_map = ref.inject or {}

        async def bound_execute(
            args: dict[str, Any],
            _fn: Any = fn,
            _cfg: dict[str, Any] = cfg_dict,
            _inj: dict[str, str] = inject_map,
            _ctx: dict[str, Any] = ctx_values,
        ) -> Any:
            merged = {**_cfg, **args}
            for arg_name, ctx_key in _inj.items():
                if arg_name not in merged:
                    val = _ctx.get(ctx_key)
                    if val is not None:
                        merged[arg_name] = val
            if "caller_agent" in _ctx:
                merged.setdefault("caller_agent", _ctx["caller_agent"])
            return await _fn(merged)

        bindings.append(ToolBinding(
            definition=definition,
            execute=bound_execute,
            source=ref.name,
        ))
    return bindings


def _truncate(value: Any, max_len: int = 500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:max_len] + ("..." if len(text) > max_len else "")
