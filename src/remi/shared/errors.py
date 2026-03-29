"""Base error types for the framework."""

from __future__ import annotations


class RemiError(Exception):
    """Root exception for all framework errors."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.__class__.__name__


class DomainError(RemiError):
    """Errors originating from domain logic."""


class ValidationError(DomainError):
    """Schema or input validation failures."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message, code="VALIDATION_ERROR")
        self.field = field


class GraphCycleError(DomainError):
    """Raised when the module graph contains a cycle."""

    def __init__(self, cycle: list[str]) -> None:
        super().__init__(f"Graph contains a cycle: {' -> '.join(cycle)}", code="GRAPH_CYCLE")
        self.cycle = cycle


class ModuleNotFoundError(DomainError):
    """Raised when a referenced module kind is not in the registry."""

    def __init__(self, kind: str) -> None:
        super().__init__(f"Module kind not registered: {kind}", code="MODULE_NOT_FOUND")
        self.kind = kind


class AppNotFoundError(DomainError):
    """Raised when an app_id is not in the registry."""

    def __init__(self, app_id: str) -> None:
        super().__init__(f"App not found: {app_id}", code="APP_NOT_FOUND")
        self.app_id = app_id


class ExecutionError(RemiError):
    """Errors during module execution."""

    def __init__(self, message: str, *, module_id: str | None = None) -> None:
        super().__init__(message, code="EXECUTION_ERROR")
        self.module_id = module_id


class StateStoreError(RemiError):
    """Errors from state persistence."""
