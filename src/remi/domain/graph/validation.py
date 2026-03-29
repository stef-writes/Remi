"""Graph validation — cycle detection, dangling edge checks, structural integrity."""

from __future__ import annotations

from collections import defaultdict, deque

from remi.domain.graph.definitions import AppDefinition
from remi.shared.errors import GraphCycleError, ValidationError
from remi.shared.ids import ModuleId
from remi.shared.result import Err, Ok, Result


def validate_graph(app: AppDefinition) -> Result[AppDefinition, list[str]]:
    """Validate an app definition's graph structure. Returns Ok(app) or Err(errors)."""
    errors: list[str] = []

    module_id_set = set(app.module_ids)
    if len(module_id_set) != len(app.modules):
        errors.append("Duplicate module IDs detected")

    for edge in app.edges:
        if edge.from_module not in module_id_set:
            errors.append(f"Edge references unknown source module: {edge.from_module}")
        if edge.to_module not in module_id_set:
            errors.append(f"Edge references unknown target module: {edge.to_module}")
        if edge.from_module == edge.to_module:
            errors.append(f"Self-loop detected on module: {edge.from_module}")

    try:
        topological_sort(app)
    except GraphCycleError as exc:
        errors.append(str(exc))

    if errors:
        return Err(errors)
    return Ok(app)


def topological_sort(app: AppDefinition) -> list[ModuleId]:
    """Kahn's algorithm — returns modules in execution order or raises GraphCycleError."""
    adjacency: dict[ModuleId, list[ModuleId]] = defaultdict(list)
    in_degree: dict[ModuleId, int] = {m.id: 0 for m in app.modules}

    for edge in app.edges:
        adjacency[edge.from_module].append(edge.to_module)
        in_degree[edge.to_module] = in_degree.get(edge.to_module, 0) + 1

    queue: deque[ModuleId] = deque(mid for mid, deg in in_degree.items() if deg == 0)
    order: list[ModuleId] = []

    while queue:
        current = queue.popleft()
        order.append(current)
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(app.modules):
        remaining = [mid for mid in app.module_ids if mid not in set(order)]
        raise GraphCycleError(remaining)

    return order
