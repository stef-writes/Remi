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
from typing import Any, Protocol

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
    AgentStepNode,
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


class AgentStepExecutor(Protocol):
    """Minimal protocol for running a named agent from a workflow step.

    Implemented by ``AgentRuntime`` — the workflow engine doesn't know
    about sessions, sandbox lifecycle, or chat threads. It only needs
    to invoke an agent by name and get back an answer.
    """

    async def ask(
        self,
        agent_name: str,
        question: str,
        *,
        session_id: str | None = None,
        mode: str = "agent",
    ) -> tuple[str | None, str]: ...


class WorkflowRunner:
    """Executes workflow DAGs with parallel scheduling."""

    def __init__(
        self,
        provider_factory: LLMProviderFactory,
        default_provider: str,
        default_model: str,
        tool_registry: ToolRegistry,
        usage_ledger: LLMUsageLedger | None = None,
        agent_executor: AgentStepExecutor | None = None,
    ) -> None:
        self._factory = provider_factory
        self._default_provider = default_provider
        self._default_model = default_model
        self._usage_ledger = usage_ledger
        self._tool_registry = tool_registry
        self._agent_executor = agent_executor

    def set_agent_executor(self, executor: AgentStepExecutor) -> None:
        """Late-bind the agent executor (breaks the circular dep with AgentRuntime)."""
        self._agent_executor = executor

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
            _log.debug(
                "step_waiting_deps",
                workflow=workflow.name,
                step=step_id,
                deps=sorted(all_deps),
                optional=sorted(optional_deps),
            )
            for dep in all_deps:
                if dep in completion_events:
                    await completion_events[dep].wait()
                    _log.debug("step_dep_resolved", step=step_id, dep=dep)

            if all_deps:
                _log.debug(
                    "step_deps_resolved",
                    workflow=workflow.name,
                    step=step_id,
                    deps=sorted(all_deps),
                )

            required_deps = all_deps - optional_deps
            if any(dep in gated_steps for dep in required_deps):
                gated_steps.add(step_id)
                sr = StepResult(step_id=step_id, value={}, gated=True)
                step_results[step_id] = sr
                step_outputs[step_id] = {}
                _log.info(
                    "step_skipped",
                    workflow=workflow.name,
                    step=step_id,
                    reason="gate",
                    gated_deps=sorted(dep for dep in required_deps if dep in gated_steps),
                )
                _emit(on_event, NodeSkipped(
                    workflow=workflow.name, node_id=step_id, reason="gate",
                ))
                completion_events[step_id].set()
                return

            if step_id in skip:
                sr = StepResult(step_id=step_id, value={}, skipped=True)
                step_results[step_id] = sr
                step_outputs[step_id] = {}
                _log.info(
                    "step_skipped",
                    workflow=workflow.name,
                    step=step_id,
                    reason="explicit",
                )
                _emit(on_event, NodeSkipped(
                    workflow=workflow.name, node_id=step_id, reason="explicit",
                ))
                completion_events[step_id].set()
                return

            if node.when and not evaluate_condition(node.when, step_outputs):
                sr = StepResult(step_id=step_id, value={}, skipped=True)
                step_results[step_id] = sr
                step_outputs[step_id] = {}
                _log.info(
                    "step_skipped",
                    workflow=workflow.name,
                    step=step_id,
                    reason="when",
                    condition=node.when,
                )
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
                _log.info(
                    "step_started",
                    workflow=workflow.name,
                    step=step_id,
                    kind=node.kind,
                )
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
                    agent_executor=self._agent_executor,
                )

            step_results[step_id] = sr
            step_outputs[step_id] = sr.value

            if sr.gated:
                gated_steps.add(step_id)

            _log.info(
                "step_completed",
                workflow=workflow.name,
                step=step_id,
                kind=node.kind,
                gated=sr.gated,
                prompt_tokens=sr.usage.prompt_tokens,
                completion_tokens=sr.usage.completion_tokens,
            )
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
    agent_executor: AgentStepExecutor | None = None,
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
                agent_executor=agent_executor,
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
# Tool resolution for llm_tools steps
# ---------------------------------------------------------------------------


def _resolve_tools_for_step(
    node: LLMToolsNode,
    tool_definitions: list[ToolDefinition] | None,
    tool_execute: ToolExecuteFn | None,
    tool_registry: ToolRegistry,
) -> tuple[list[ToolDefinition], ToolExecuteFn]:
    """Resolve tool definitions and executor for an llm_tools step.

    If the caller supplied ``tool_execute``, filter definitions by the
    step's declared tool names and use the caller's executor. Otherwise,
    auto-build both from the shared ``ToolRegistry`` using flat name
    lookups (workflow steps don't carry per-tool ``ToolRef`` config).
    """
    step_tool_names = list(node.tools)

    if tool_execute is not None:
        if step_tool_names and tool_definitions:
            filtered = [td for td in tool_definitions if td.name in set(step_tool_names)]
        else:
            filtered = tool_definitions or []
        return filtered, tool_execute

    if step_tool_names and tool_registry is not None:
        resolved_defs = tool_registry.list_definitions(names=step_tool_names)
        if resolved_defs:
            async def _registry_execute(name: str, arguments: dict[str, Any]) -> Any:
                entry = tool_registry.get(name)
                if entry is None:
                    return {"error": f"Tool '{name}' not found in registry"}
                fn, _ = entry
                return await fn(arguments)

            return resolved_defs, _registry_execute

    raise ValueError(
        f"Node '{node.id}' is llm_tools but no tool_execute was provided "
        f"and tools {step_tool_names!r} could not be resolved from the registry"
    )


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
    agent_executor: AgentStepExecutor | None = None,
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
        resolved_defs, resolved_execute = _resolve_tools_for_step(
            node, tool_definitions, tool_execute, tool_registry,
        )

        return await run_llm_tools_step(
            node,
            workflow_input,
            step_outputs,
            context,
            defaults,
            provider_factory,
            usage_ledger,
            resolved_defs,
            resolved_execute,
            output_schemas,
            workflow_name=workflow_name,
        )

    if isinstance(node, TransformNode):
        return await run_transform_step(node, step_outputs, tool_registry, port_data)

    if isinstance(node, ForEachNode):
        return await run_for_each_step(node, step_outputs, tool_registry)

    if isinstance(node, GateNode):
        return await run_gate_step(node, step_outputs)

    if isinstance(node, AgentStepNode):
        return await _run_agent_step(node, workflow_input, step_outputs, agent_executor)

    raise ValueError(f"Unknown node type: {type(node).__name__}")


async def _run_agent_step(
    node: AgentStepNode,
    workflow_input: str,
    step_outputs: dict[str, StepValue],
    agent_executor: AgentStepExecutor | None,
) -> StepResult:
    """Execute a full AgentNode loop as a workflow step."""
    if agent_executor is None:
        raise RuntimeError(
            f"Workflow step '{node.id}' is kind: agent but no agent_executor "
            f"was provided to WorkflowRunner. Call set_agent_executor() or "
            f"pass agent_executor at construction time."
        )

    from remi.agent.workflow.resolve import resolve_template

    prompt = resolve_template(node.input_template, workflow_input, step_outputs)

    _log.info(
        "agent_step_start",
        step_id=node.id,
        agent_name=node.agent_name,
        prompt_length=len(prompt),
    )

    answer, run_id = await agent_executor.ask(
        node.agent_name,
        prompt,
        mode=node.mode,
    )

    _log.info(
        "agent_step_done",
        step_id=node.id,
        agent_name=node.agent_name,
        run_id=run_id,
        answer_length=len(answer) if answer else 0,
    )

    return StepResult(
        step_id=node.id,
        value=answer or "",
    )
