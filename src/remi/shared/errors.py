"""Typed error hierarchy for the framework.

Every application-level exception inherits from ``RemiError`` so that
global handlers (HTTP, JSON-RPC, CLI) can translate errors into
structured responses with a machine-readable ``code``, human-readable
message, and contextual attributes for logging/tracing.
"""

from __future__ import annotations


class RemiError(Exception):
    """Root exception for all framework errors."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.__class__.__name__

    def to_dict(self) -> dict[str, object]:
        """Structured representation for logging and API responses."""
        return {"code": self.code, "message": str(self)}


# ---------------------------------------------------------------------------
# Domain errors — bad input, missing entities, logic violations
# ---------------------------------------------------------------------------


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


class SessionNotFoundError(DomainError):
    """Chat session does not exist."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session not found: {session_id}", code="SESSION_NOT_FOUND")
        self.session_id = session_id


class AgentConfigError(DomainError):
    """Agent YAML or runtime config is invalid."""

    def __init__(self, agent_id: str, reason: str) -> None:
        super().__init__(f"Agent config invalid ({agent_id}): {reason}", code="AGENT_CONFIG_ERROR")
        self.agent_id = agent_id
        self.reason = reason


# ---------------------------------------------------------------------------
# Execution errors — runtime failures during processing
# ---------------------------------------------------------------------------


class ExecutionError(RemiError):
    """Errors during module execution."""

    def __init__(self, message: str, *, module_id: str | None = None) -> None:
        super().__init__(message, code="EXECUTION_ERROR")
        self.module_id = module_id


class LLMError(ExecutionError):
    """LLM provider call failed."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str | None = None,
        transient: bool = False,
    ) -> None:
        super().__init__(message, module_id=None)
        self.code = "LLM_ERROR"
        self.provider = provider
        self.model = model
        self.transient = transient


class ToolError(ExecutionError):
    """Tool invocation failed."""

    def __init__(
        self,
        message: str,
        *,
        tool_name: str,
        call_id: str | None = None,
    ) -> None:
        super().__init__(message, module_id=None)
        self.code = "TOOL_ERROR"
        self.tool_name = tool_name
        self.call_id = call_id


class RetryExhaustedError(ExecutionError):
    """All retry attempts failed."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_error: Exception | None = None,
    ) -> None:
        super().__init__(message, module_id=None)
        self.code = "RETRY_EXHAUSTED"
        self.attempts = attempts
        self.last_error = last_error


class IngestionError(RemiError):
    """Document ingestion or classification failed."""

    def __init__(self, message: str, *, doc_id: str | None = None) -> None:
        super().__init__(message, code="INGESTION_ERROR")
        self.doc_id = doc_id


# ---------------------------------------------------------------------------
# Infrastructure errors
# ---------------------------------------------------------------------------


class StateStoreError(RemiError):
    """Errors from state persistence."""
