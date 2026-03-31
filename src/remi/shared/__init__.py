"""Incline: Shared utilities — clock, IDs, errors, result types."""

from remi.shared.clock import Clock, FixedClock, SystemClock
from remi.shared.enums import (
    ExecutionMode,
    ModuleCategory,
    ModuleStatus,
    RunStatus,
    StateStoreBackend,
)
from remi.shared.errors import (
    AgentConfigError,
    AppNotFoundError,
    DomainError,
    ExecutionError,
    GraphCycleError,
    IngestionError,
    LLMError,
    ModuleNotFoundError,
    RemiError,
    RetryExhaustedError,
    SessionNotFoundError,
    StateStoreError,
    ToolError,
    ValidationError,
)
from remi.shared.ids import ActorId, AppId, EdgeId, ModuleId, RunId, new_edge_id, new_run_id
from remi.shared.result import Err, Ok, Result

__all__ = [
    "ActorId",
    "AgentConfigError",
    "AppId",
    "AppNotFoundError",
    "Clock",
    "DomainError",
    "EdgeId",
    "Err",
    "ExecutionError",
    "ExecutionMode",
    "FixedClock",
    "GraphCycleError",
    "IngestionError",
    "LLMError",
    "ModuleCategory",
    "ModuleId",
    "ModuleNotFoundError",
    "ModuleStatus",
    "Ok",
    "RemiError",
    "Result",
    "RetryExhaustedError",
    "RunId",
    "RunStatus",
    "SessionNotFoundError",
    "StateStoreBackend",
    "StateStoreError",
    "SystemClock",
    "ToolError",
    "ValidationError",
    "new_edge_id",
    "new_run_id",
]
