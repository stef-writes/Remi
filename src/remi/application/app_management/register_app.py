"""Use case: register a new app definition into the registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from remi.domain.graph.validation import validate_graph
from remi.shared.result import Err, Ok, Result

if TYPE_CHECKING:
    from remi.application.app_management.ports import AppRegistry
    from remi.domain.graph.definitions import AppDefinition
    from remi.domain.modules.ports import ModuleRegistry


class RegisterAppUseCase:
    def __init__(self, app_registry: AppRegistry, module_registry: ModuleRegistry) -> None:
        self._app_registry = app_registry
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

        self._app_registry.register(app)
        return Ok(app)
