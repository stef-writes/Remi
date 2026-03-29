"""Conditional router module — branches graph execution based on data."""

from __future__ import annotations

from typing import Any

from remi.domain.modules.base import BaseModule, ModuleOutput
from remi.runtime.context.runtime_context import RuntimeContext


class ConditionalRouterModule(BaseModule):
    """Evaluates a condition and forwards the appropriate branch label.

    Config keys:
        field:      key to inspect in the upstream value
        conditions: list of {operator, value, label} dicts
        default:    fallback label when no condition matches

    Output value is the full upstream data; the ``contract`` is set to
    the matched label so downstream edge conditions can gate on it.
    """

    kind = "conditional_router"

    async def run(self, inputs: dict[str, Any], context: RuntimeContext) -> ModuleOutput:
        upstream = _get_first_upstream(inputs)

        field = self.config.get("field", "")
        conditions = self.config.get("conditions", [])
        default_label = self.config.get("default", "default")

        if isinstance(upstream, dict):
            field_value = upstream.get(field)
        else:
            field_value = upstream

        matched_label = default_label
        for cond in conditions:
            if _evaluate(field_value, cond.get("operator", "eq"), cond.get("value")):
                matched_label = cond.get("label", default_label)
                break

        return ModuleOutput(
            value=upstream,
            contract=f"route:{matched_label}",
            metadata={"matched_label": matched_label, "field": field},
        )


_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and b is not None and a > b,
    "gte": lambda a, b: a is not None and b is not None and a >= b,
    "lt": lambda a, b: a is not None and b is not None and a < b,
    "lte": lambda a, b: a is not None and b is not None and a <= b,
    "in": lambda a, b: a in b if isinstance(b, (list, set, tuple)) else False,
    "contains": lambda a, b: b in a if isinstance(a, str) else False,
}


def _evaluate(field_value: Any, operator: str, compare_value: Any) -> bool:
    fn = _OPS.get(operator)
    if fn is None:
        return False
    try:
        return fn(field_value, compare_value)
    except (TypeError, ValueError):
        return False


def _get_first_upstream(inputs: dict[str, Any]) -> Any:
    if not inputs:
        return None
    return next(iter(inputs.values()))
