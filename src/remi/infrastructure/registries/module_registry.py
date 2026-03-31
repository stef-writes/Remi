"""In-memory module registry — maps kind strings to module classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from remi.domain.modules.ports import ModuleRegistry
from remi.shared.errors import ModuleNotFoundError

if TYPE_CHECKING:
    from remi.domain.graph.definitions import ModuleDefinition
    from remi.domain.modules.base import BaseModule


class InMemoryModuleRegistry(ModuleRegistry):
    def __init__(self) -> None:
        self._registry: dict[str, type[BaseModule]] = {}

    def register(self, kind: str, module_class: type[BaseModule]) -> None:
        self._registry[kind] = module_class

    def get_class(self, kind: str) -> type[BaseModule]:
        cls = self._registry.get(kind)
        if cls is None:
            raise ModuleNotFoundError(kind)
        return cls

    def build(self, definition: ModuleDefinition) -> BaseModule:
        cls = self.get_class(definition.kind)
        return cls(config=definition.config)

    def has(self, kind: str) -> bool:
        return kind in self._registry

    def list_kinds(self) -> list[str]:
        return sorted(self._registry.keys())
