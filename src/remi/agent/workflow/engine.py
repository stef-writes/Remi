"""Workflow engine — DAG scheduler with parallel step execution.

Builds a dependency graph from node ``depends_on`` and ``Wire``
connections, dispatches nodes through an ``asyncio.Semaphore``, and
emits structured ``NodeEvent`` objects for observability.

Features:
  - Typed Pydantic node models (LLMNode, TransformNode, ForEachNode, GateNode)
  - Wire-based structured data routing between nodes
  - Retry policies with configurable backoff
  - Output schema validation via Pydantic models
  - Event callbacks for real-time UI updates
  - Gate propagation and inline ``when`` conditions
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from remi.agent.llm.factory import LLMProviderFactory
from remi.agent.llm.types import ToolDefinition
from remi.agent.observe.usage import LLMUsageLedger
from remi.agent.types import ToolRegistry
from remi.agent.workflow.plan import build_execution_plan
from remi.agent.workflow.resolve import evaluate_condition
from remi.agent.workflow.steps import (
    OutputSchemaRegistry,
    ToolExecuteFn,
    run_for_each_step,
    run_gate_step,
    run_llm_step,
    run_llm_tools_step,
    run_transform_step,
)
from remi.agent.workflow.types import (
    EventCallback,
    ForEachNode,
    GateNode,
    InboundBinding,
    LLMNode,
    LLMToolsNode,
    NodeCompleted,
    NodeEvent,
    NodeFailed,
    NodeRetrying,
    NodeSkipped,
    NodeStarted,
    StepResult,
    StepValue,
    TransformNode,
    WorkflowDef,
    WorkflowDefaults,
    WorkflowNode,
    WorkflowResult,
)

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Port data routing
# ---------------------------------------------------------------------------


def _route_port_data(
    step_id: str,
    inbound: tuple[InboundBinding, ...],
    step_outputs: dict[str, StepValue],
) -> dict[str, Any]:
    """Build a dict of routed input port values from upstream wires."""
    routed: dict[str, Any] = {}
    for binding in inbound:
        src_output = step_outputs.get(binding.source_step)
        if src_output is None:
            continue
        if isinstance(src_output, dict):
            routed[binding.target_port] = src_output.get(
                binding.source_port, src_output
            )
        else:
            routed[binding.target_port] = src_output
    return routed


# ---------------------------------------------------------------------------
# Event emission helper
# ---------------------------------------------------------------------------


def _emit(callback: EventCallback | None, event: NodeEvent) -> None:
    if callback is not None:
        callback(event)


# ---------------------------------------------------------------------------
# WorkflowRunner
# ---------------------------------------------------------------------------


class WorkflowRunner:
    """Executes workflow DAGs with parallel scheduling."""

    def __init__(
        self,
        provider_factory: LLMProviderFactory,
        default_provider: str,
        default_model: str,
        tool_registry: ToolRegistry,
        usage_ledger: LLMUsageLedger | None = None,
    ) -> None:
        self._factory = provider_factory
        self._default_provider = default_provider
        self._default_model = default_model
        self._usage_ledger = usage_ledger
        self._tool_registry = tool_registry

    async def run(
        self,
        workflow: WorkflowDef,
        workflow_input: str,
        *,
        context: dict[str, str] | None = None,
        skip_steps: set[str] | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
        tool_execute: ToolExecuteFn | None = None,
        output_schemas: OutputSchemaRegistry | None = None,
        on_event: EventCallback | None = None,
    ) -> WorkflowResult:
        """Execute the workflow and return accumulated results."""
        skip = skip_steps or set()
        output_schemas = output_schemas or {}

        defaults = workflow.defaults
        if not defaults.provider:
            defaults = WorkflowDefaults(
                provider=self._default_provider,
                model=defaults.model or self._default_model,
                max_concurrency=defaults.max_concurrency,
            )
        elif not defaults.model:
            defaults = WorkflowDefaults(
                provider=defaults.provider,
                model=self._default_model,
                max_concurrency=defaults.max_concurrency,
            )

        plan = build_execution_plan(workflow)
        semaphore = asyncio.Semaphore(defaults.max_concurrency)

        step_outputs: dict[str, StepValue] = {}
        step_results: dict[str, StepResult] = {}
        gated_steps: set[str] = set()
        completion_events: dict[str, asyncio.Event] = {
            s.id: asyncio.Event() for s in workflow.steps
        }

        _log.info(
            "workflow_start",
            workflow=workflow.name,
            step_count=len(workflow.steps),
            wire_count=len(workflow.wires),
            skipped=list(skip) if skip else [],
            max_concurrency=defaults.max_concurrency,
        )

        async def execute_step(step_id: str) -> None:
            node = workflow.get_step(step_id)
            if node is None:
                return

            all_deps = set(node.depends_on)
            optional_deps: set[str] = set()
            for binding in plan.inbound.get(step_id, ()):
                all_deps.add(binding.source_step)
                if binding.optional:
                    optional_deps.add(binding.source_step)
            for dep in all_deps:
                if dep in completion_events:
                    await completion_events[dep].wait()

            required_deps = all_deps - optional_deps
            if any(dep in gated_steps for dep in required_deps):
                gated_steps.add(step_id)
                sr = StepResult(step_id=step_id, value={}, gated=True)
                step_results[step_id] = sr
                step_outputs[step_id] = {}
                _emit(on_event, NodeSkipped(
                    workflow=workflow.name, node_id=step_id, reason="gate",
                ))
                completion_events[step_id].set()
                return

            if step_id in skip:
                sr = StepResult(step_id=step_id, value={}, skipped=True)
                step_results[step_id] = sr
                step_outputs[step_id] = {}
                _emit(on_event, NodeSkipped(
                    workflow=workflow.name, node_id=step_id, reason="explicit",
                ))
                completion_events[step_id].set()
                return

            if node.when and not evaluate_condition(node.when, step_outputs):
                sr = StepResult(step_id=step_id, value={}, skipped=True)
                step_results[step_id] = sr
                step_outputs[step_id] = {}
                _emit(on_event, NodeSkipped(
                    workflow=workflow.name, node_id=step_id, reason="when",
                ))
                completion_events[step_id].set()
                return

            port_data = _route_port_data(
                step_id,
                plan.inbound.get(step_id, ()),
                step_outputs,
            )

            async with semaphore:
                _emit(on_event, NodeStarted(
                    workflow=workflow.name, node_id=step_id, kind=node.kind,
                ))
                sr = await _dispatch_with_retry(
                    node=node,
                    workflow_input=workflow_input,
                    step_outputs=step_outputs,
                    port_data=port_data,
                    context=context,
                    defaults=defaults,
                    provider_factory=self._factory,
                    usage_ledger=self._usage_ledger,
                    tool_definitions=tool_definitions,
                    tool_execute=tool_execute,
                    output_schemas=output_schemas,
                    tool_registry=self._tool_registry,
                    workflow_name=workflow.name,
                    on_event=on_event,
                )

            step_results[step_id] = sr
            step_outputs[step_id] = sr.value

            if sr.gated:
                gated_steps.add(step_id)

            _emit(on_event, NodeCompleted(
                workflow=workflow.name, node_id=step_id, usage=sr.usage,
            ))
            completion_events[step_id].set()

        tasks = [asyncio.create_task(execute_step(s.id)) for s in workflow.steps]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                step_id = workflow.steps[i].id
                _log.error(
                    "workflow_step_failed",
                    workflow=workflow.name,
                    step=step_id,
                    error=str(result),
                    exc_info=result,
                )
                _emit(on_event, NodeFailed(
                    workflow=workflow.name, node_id=step_id, error=str(result),
                ))
                if not completion_events[step_id].is_set():
                    gated_steps.add(step_id)
                    step_outputs[step_id] = {}
                    completion_events[step_id].set()

        wf_result = WorkflowResult()
        for step in workflow.steps:
            if step.id in step_results:
                sr = step_results[step.id]
                wf_result.steps.append(sr)
                wf_result.total_usage = wf_result.total_usage + sr.usage

        _log.info(
            "workflow_done",
            workflow=workflow.name,
            total_prompt_tokens=wf_result.total_usage.prompt_tokens,
            total_completion_tokens=wf_result.total_usage.completion_tokens,
            steps_completed=len(wf_result.steps),
            steps_gated=len(gated_steps),
        )
        return wf_result


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------


async def _dispatch_with_retry(
    *,
    node: WorkflowNode,
    workflow_input: str,
    step_outputs: dict[str, StepValue],
    port_data: dict[str, Any],
    context: dict[str, str] | None,
    defaults: WorkflowDefaults,
    provider_factory: LLMProviderFactory,
    usage_ledger: LLMUsageLedger | None,
    tool_definitions: list[ToolDefinition] | None,
    tool_execute: ToolExecuteFn | None,
    output_schemas: OutputSchemaRegistry,
    tool_registry: ToolRegistry,
    workflow_name: str,
    on_event: EventCallback | None,
) -> StepResult:
    """Dispatch a node with optional retry policy."""
    policy = node.retry
    max_attempts = policy.max_attempts if policy else 1

    for attempt in range(1, max_attempts + 1):
        try:
            return await _dispatch_step(
                node=node,
                workflow_input=workflow_input,
                step_outputs=step_outputs,
                port_data=port_data,
                context=context,
                defaults=defaults,
                provider_factory=provider_factory,
                usage_ledger=usage_ledger,
                tool_definitions=tool_definitions,
                tool_execute=tool_execute,
                output_schemas=output_schemas,
                tool_registry=tool_registry,
                workflow_name=workflow_name,
            )
        except Exception as exc:
            if policy and attempt < max_attempts:
                delay = policy.delay_for(attempt)
                _log.warning(
                    "node_retry",
                    workflow=workflow_name,
                    node=node.id,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    delay=delay,
                    error=str(exc),
                    exc_info=True,
                )
                _emit(on_event, NodeRetrying(
                    workflow=workflow_name,
                    node_id=node.id,
                    attempt=attempt,
                    error=str(exc),
                ))
                if delay > 0:
                    await asyncio.sleep(delay)
                continue
            raise

    raise RuntimeError(f"Exhausted {max_attempts} retry attempts for node '{node.id}'")


# ---------------------------------------------------------------------------
# Step dispatch
# ---------------------------------------------------------------------------


async def _dispatch_step(
    *,
    node: WorkflowNode,
    workflow_input: str,
    step_outputs: dict[str, StepValue],
    port_data: dict[str, Any],
    context: dict[str, str] | None,
    defaults: WorkflowDefaults,
    provider_factory: LLMProviderFactory,
    usage_ledger: LLMUsageLedger | None,
    tool_definitions: list[ToolDefinition] | None,
    tool_execute: ToolExecuteFn | None,
    output_schemas: OutputSchemaRegistry,
    tool_registry: ToolRegistry,
    workflow_name: str,
) -> StepResult:
    """Route a node to its executor based on kind."""

    if isinstance(node, LLMNode):
        return await run_llm_step(
            node,
            workflow_input,
            step_outputs,
            context,
            defaults,
            provider_factory,
            usage_ledger,
            output_schemas,
            workflow_name=workflow_name,
        )

    if isinstance(node, LLMToolsNode):
        if tool_execute is None:
            raise ValueError(f"Node '{node.id}' is llm_tools but no tool_execute was provided")
        step_tool_names = set(node.tools)
        if step_tool_names and tool_definitions:
            filtered_defs = [td for td in tool_definitions if td.name in step_tool_names]
        else:
            filtered_defs = tool_definitions or []

        return await run_llm_tools_step(
            node,
            workflow_input,
            step_outputs,
            context,
            defaults,
            provider_factory,
            usage_ledger,
            filtered_defs,
            tool_execute,
            output_schemas,
            workflow_name=workflow_name,
        )

    if isinstance(node, TransformNode):
        return await run_transform_step(node, step_outputs, tool_registry, port_data)

    if isinstance(node, ForEachNode):
        return await run_for_each_step(node, step_outputs, tool_registry)

    if isinstance(node, GateNode):
        return await run_gate_step(node, step_outputs)

    raise ValueError(f"Unknown node type: {type(node).__name__}")
