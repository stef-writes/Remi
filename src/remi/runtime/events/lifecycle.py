"""Lifecycle event definitions emitted during graph execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from remi.shared.ids import AppId, ModuleId, RunId

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class LifecycleEvent:
    """Base class for all runtime lifecycle events."""

    event_type: str
    app_id: AppId
    run_id: RunId
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModuleEvent(LifecycleEvent):
    """Event scoped to a specific module execution."""

    module_id: ModuleId = ModuleId("")
    error: str | None = None


@dataclass(frozen=True)
class InterAppEvent(LifecycleEvent):
    """Event that crosses app boundaries for mesh-layer orchestration."""

    source_app_id: AppId = AppId("")
    target_app_id: AppId | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None


MODULE_STARTED = "module.started"
MODULE_COMPLETED = "module.completed"
MODULE_FAILED = "module.failed"
RUN_STARTED = "run.started"
RUN_COMPLETED = "run.completed"
RUN_FAILED = "run.failed"

APP_TRIGGER = "app.trigger"
APP_OUTPUT_READY = "app.output_ready"
APP_CHAIN = "app.chain"
