"""Framework-wide enumerations."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class ExecutionMode(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    REPLAY = "replay"
    DRY_RUN = "dry_run"
    AGENT_DRIVEN = "agent_driven"


@unique
class ModuleStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@unique
class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@unique
class ModuleCategory(StrEnum):
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
class StateStoreBackend(StrEnum):
    IN_MEMORY = "in_memory"
    POSTGRES = "postgres"
    REDIS = "redis"
