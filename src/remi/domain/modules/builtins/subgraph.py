"""Subgraph module — spawns a child graph run and returns its outputs."""

from __future__ import annotations

from typing import Any

from remi.domain.modules.base import BaseModule, ModuleOutput
from remi.runtime.context.runtime_context import RuntimeContext
from remi.shared.ids import AppId


class SubgraphModule(BaseModule):
    """Spawns a child graph run and awaits its result.

    Config keys:
        app_id:  the app to run as a child graph
        params:  static params merged with upstream inputs
    """

    kind = "subgraph"

    async def run(self, inputs: dict[str, Any], context: RuntimeContext) -> ModuleOutput:
        graph_runner = context.extras.get("graph_runner")
        app_registry = context.extras.get("app_registry")
        state_store = context.extras.get("state_store")

        if not graph_runner or not app_registry:
            raise RuntimeError("Subgraph module requires graph_runner and app_registry in context")

        child_app_id = AppId(self.config.get("app_id", ""))
        child_app = app_registry.get(child_app_id)
        if child_app is None:
            raise RuntimeError(f"Child app not found: {child_app_id}")

        static_params = dict(self.config.get("params", {}))
        flat_inputs: dict[str, Any] = {}
        for val in inputs.values():
            if isinstance(val, dict):
                flat_inputs.update(val)
        run_params = {**static_params, **flat_inputs}

        child_run_id = await graph_runner.run(
            child_app,
            run_params=run_params,
        )

        outputs: dict[str, Any] = {}
        if state_store:
            all_states = await state_store.get_all_module_states(child_app_id, child_run_id)
            for s in all_states:
                if s.output is not None:
                    outputs[s.module_id] = {
                        "contract": s.contract,
                        "output": s.output,
                    }

        return ModuleOutput(
            value=outputs,
            contract="subgraph_result",
            metadata={"child_app_id": child_app_id, "child_run_id": child_run_id},
        )
