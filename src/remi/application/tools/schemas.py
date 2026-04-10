"""Result schema inference — maps tool calls to frontend card schema labels.

This is application-layer knowledge: the frontend card registry is driven
by the same domain concepts (CLI operations, query operations) that live in
``application/``. The agent kernel is schema-agnostic; this callable is
injected at startup via ``AgentRuntime.set_result_schema_fn``.
"""

from __future__ import annotations

# Maps substrings in bash command arguments to a result_schema label.
# The frontend uses these to pick which card component to render.
_RESULT_SCHEMA_PATTERNS: list[tuple[str, str]] = [
    ("portfolio managers", "managers_list"),
    ("portfolio properties", "properties_list"),
    ("portfolio rent-roll", "rent_roll"),
    ("portfolio manager-review", "manager_review"),
    ("portfolio rankings", "manager_rankings"),
    ("operations delinquency", "delinquency"),
    ("operations leases", "leases_list"),
    ("operations maintenance", "maintenance_list"),
    ("operations expiring-leases", "expiring_leases"),
    ("intelligence dashboard", "dashboard_overview"),
    ("intelligence vacancies", "vacancies"),
    ("intelligence trends", "trends"),
    ("intelligence search", "search_results"),
]

_QUERY_OPERATION_SCHEMAS: dict[str, str] = {
    "dashboard": "dashboard_overview",
    "managers": "managers_list",
    "manager_review": "manager_review",
    "properties": "properties_list",
    "rent_roll": "rent_roll",
    "rankings": "manager_rankings",
    "delinquency": "delinquency",
    "expiring_leases": "expiring_leases",
    "vacancies": "vacancies",
    "leases": "leases_list",
    "maintenance": "maintenance_list",
    "search": "search_results",
    "delinquency_trend": "trends",
    "occupancy_trend": "trends",
    "rent_trend": "trends",
    "maintenance_trend": "trends",
}


def infer_result_schema(tool_name: str, arguments: dict[str, object]) -> str | None:
    """Return a result_schema label for the given tool call, or None.

    Called by the agent loop after each tool execution. The returned label
    is forwarded to the frontend as ``result_schema`` on the ``tool_result``
    stream event so the UI can render the appropriate card.
    """
    if tool_name == "query":
        operation = arguments.get("operation", "")
        return _QUERY_OPERATION_SCHEMAS.get(str(operation))

    if tool_name not in ("bash", "sandbox_exec_shell"):
        return None

    cmd = arguments.get("command", "") or arguments.get("cmd", "") or ""
    if not isinstance(cmd, str):
        return None

    cmd_lower = cmd.lower()
    for pattern, schema in _RESULT_SCHEMA_PATTERNS:
        if pattern in cmd_lower:
            return schema

    return None
