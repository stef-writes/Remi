"""Framework-wide enumerations."""

from __future__ import annotations

from enum import Enum, unique


@unique
class ExecutionMode(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    REPLAY = "replay"
    DRY_RUN = "dry_run"
    AGENT_DRIVEN = "agent_driven"


@unique
class ModuleStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@unique
class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@unique
class ModuleCategory(str, Enum):
    DATA_ACQUISITION = "data_acquisition"
    TRANSFORM = "transform"
    METRIC = "metric"
    RULE = "rule"
    VIEWMODEL = "viewmodel"
    LLM = "llm"
    ACTION = "action"
    PLANNER = "planner"
    ORCHESTRATOR = "orchestrator"


@unique
class StateStoreBackend(str, Enum):
    IN_MEMORY = "in_memory"
    POSTGRES = "postgres"
    REDIS = "redis"
