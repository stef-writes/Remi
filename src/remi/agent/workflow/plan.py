"""Execution plan compilation — topological sort, parallel groups, wire routing.

Compiles a ``WorkflowDef`` into an ``ExecutionPlan`` that the engine can
execute without re-computing graph structure on every run.

The plan merges three dependency sources:
  1. Explicit ``depends_on`` declared on each node.
  2. Implicit dependencies from ``Wire`` connections.
  3. Implicit dependencies from ``ForEachNode.items_from`` dot-paths.
"""

from __future__ import annotations

from collections import deque

from remi.agent.workflow.types import (
    ExecutionPlan,
    ForEachNode,
    InboundBinding,
    WorkflowDef,
)


def build_execution_plan(workflow: WorkflowDef) -> ExecutionPlan:
    """Compile a WorkflowDef into a runtime-ready ExecutionPlan."""
    step_ids = workflow.step_ids()

    predecessors: dict[str, set[str]] = {sid: set() for sid in step_ids}
    for step in workflow.steps:
        for dep in step.depends_on:
            if dep not in step_ids:
                raise ValueError(
                    f"Step '{step.id}' depends on '{dep}' which does not exist "
                    f"in workflow '{workflow.name}'"
                )
            predecessors[step.id].add(dep)

        if isinstance(step, ForEachNode) and step.items_from:
            source_step = _extract_step_from_path(step.items_from)
            if source_step and source_step in step_ids:
                predecessors[step.id].add(source_step)

    for wire in workflow.wires:
        if wire.source_step not in step_ids:
            raise ValueError(
                f"Wire source step '{wire.source_step}' does not exist "
                f"in workflow '{workflow.name}'"
            )
        if wire.target_step not in step_ids:
            raise ValueError(
                f"Wire target step '{wire.target_step}' does not exist "
                f"in workflow '{workflow.name}'"
            )
        if not wire.optional:
            predecessors[wire.target_step].add(wire.source_step)

    order = _topological_sort(predecessors, workflow.name)
    groups = _parallel_groups(predecessors)
    inbound = _build_inbound(workflow)

    return ExecutionPlan(
        workflow=workflow,
        order=tuple(order),
        groups=tuple(tuple(g) for g in groups),
        inbound=inbound,
    )


def _extract_step_from_path(path: str) -> str | None:
    """Extract the step ID from a dot-path like ``steps.validate.accepted``."""
    if path.startswith("steps."):
        path = path[6:]
    parts = path.split(".", 1)
    return parts[0] if parts[0] else None


def _topological_sort(
    predecessors: dict[str, set[str]],
    workflow_name: str,
) -> list[str]:
    """Kahn's algorithm — returns step IDs in execution order."""
    in_degree = {sid: len(preds) for sid, preds in predecessors.items()}
    queue: deque[str] = deque(sorted(sid for sid, deg in in_degree.items() if deg == 0))
    result: list[str] = []

    successors: dict[str, list[str]] = {sid: [] for sid in predecessors}
    for sid, preds in predecessors.items():
        for pred in preds:
            successors[pred].append(sid)

    while queue:
        node = queue.popleft()
        result.append(node)
        for child in sorted(successors[node]):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(result) != len(predecessors):
        raise ValueError(f"Cycle detected in workflow '{workflow_name}'")

    return result


def _parallel_groups(
    predecessors: dict[str, set[str]],
) -> list[list[str]]:
    """Compute parallel execution groups by depth level."""
    if not predecessors:
        return []

    level: dict[str, int] = {}
    remaining = set(predecessors.keys())

    while remaining:
        ready = sorted(
            sid for sid in remaining
            if all(p in level for p in predecessors[sid])
        )
        if not ready:
            raise ValueError("Cycle detected in workflow")
        for sid in ready:
            dep_level = max((level[p] for p in predecessors[sid]), default=-1)
            level[sid] = dep_level + 1
        remaining -= set(ready)

    max_level = max(level.values(), default=0)
    groups: list[list[str]] = [[] for _ in range(max_level + 1)]
    for sid, lvl in sorted(level.items(), key=lambda x: (x[1], x[0])):
        groups[lvl].append(sid)

    return groups


def _build_inbound(
    workflow: WorkflowDef,
) -> dict[str, tuple[InboundBinding, ...]]:
    """Build the per-step inbound binding index from wires."""
    inbound: dict[str, list[InboundBinding]] = {
        s.id: [] for s in workflow.steps
    }
    for wire in workflow.wires:
        inbound.setdefault(wire.target_step, []).append(
            InboundBinding(
                target_port=wire.target_port,
                source_step=wire.source_step,
                source_port=wire.source_port,
                optional=wire.optional,
            )
        )

    return {
        sid: tuple(sorted(
            bindings,
            key=lambda b: (b.target_port, b.source_step, b.source_port),
        ))
        for sid, bindings in inbound.items()
    }
