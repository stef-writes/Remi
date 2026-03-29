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
    AppNotFoundError,
    RemiError,
    DomainError,
    ExecutionError,
    GraphCycleError,
    ModuleNotFoundError,
    StateStoreError,
    ValidationError,
)
from remi.shared.ids import ActorId, AppId, EdgeId, ModuleId, RunId, new_edge_id, new_run_id
from remi.shared.result import Err, Ok, Result

__all__ = [
    "ActorId",
    "AppId",
    "AppNotFoundError",
    "RemiError",
    "Clock",
    "DomainError",
    "EdgeId",
    "Err",
    "ExecutionError",
    "ExecutionMode",
    "FixedClock",
    "GraphCycleError",
    "ModuleCategory",
    "ModuleId",
    "ModuleNotFoundError",
    "ModuleStatus",
    "Ok",
    "Result",
    "RunId",
    "RunStatus",
    "StateStoreBackend",
    "StateStoreError",
    "SystemClock",
    "ValidationError",
    "new_edge_id",
    "new_run_id",
]
