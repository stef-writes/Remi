"""Use case: validate an app definition without registering it."""

from __future__ import annotations

from remi.domain.graph.definitions import AppDefinition
from remi.domain.graph.validation import validate_graph
from remi.domain.modules.ports import ModuleRegistry
from remi.shared.result import Err, Ok, Result


class ValidateAppUseCase:
    def __init__(self, module_registry: ModuleRegistry) -> None:
        self._module_registry = module_registry

    def execute(self, app: AppDefinition) -> Result[AppDefinition, list[str]]:
        graph_result = validate_graph(app)
        if graph_result.is_err:
            return graph_result

        errors: list[str] = []
        for module_def in app.modules:
            if not self._module_registry.has(module_def.kind):
                errors.append(f"Unknown module kind: {module_def.kind}")

        if errors:
            return Err(errors)

        return Ok(app)
