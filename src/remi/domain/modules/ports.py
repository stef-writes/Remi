"""Ports (interfaces) for the module subsystem."""

from __future__ import annotations

import abc
from typing import Any

from remi.domain.graph.definitions import ModuleDefinition
from remi.domain.modules.base import BaseModule


class ModuleRegistry(abc.ABC):
    """Port: maps module `kind` strings to module classes and builds instances."""

    @abc.abstractmethod
    def register(self, kind: str, module_class: type[BaseModule]) -> None: ...

    @abc.abstractmethod
    def get_class(self, kind: str) -> type[BaseModule]: ...

    @abc.abstractmethod
    def build(self, definition: ModuleDefinition) -> BaseModule: ...

    @abc.abstractmethod
    def has(self, kind: str) -> bool: ...

    @abc.abstractmethod
    def list_kinds(self) -> list[str]: ...

    def describe_kind(self, kind: str) -> dict[str, Any]:
        """Return LLM-readable metadata about a module kind."""
        cls = self.get_class(kind)
        instance = cls()
        return instance.describe()
